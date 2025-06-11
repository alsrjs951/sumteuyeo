import torch
import torch.nn as nn
from transformers import RobertaForSequenceClassification, get_linear_schedule_with_warmup
from torch.utils.data import Dataset, DataLoader
import torch.cuda.amp as amp
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
from tqdm import tqdm
import os
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from torch.nn.functional import softmax
import sys
import random


# 1. Pointwise 학습/평가용 데이터셋 클래스 -------------------------
# (기존 KReRankingEvalDataset과 동일 구조, 학습/평가에 모두 사용)
class PointwiseRankingDataset(Dataset):
    """
    Pointwise 학습과 평가를 위한 데이터셋.
    각 (query, item, score) 쌍을 개별 데이터로 처리합니다.
    """

    def __init__(self, data_path, tokenizer, max_length=256):
        self.tokenizer = tokenizer
        self.max_length = max_length
        # 파일이 존재하지 않을 경우를 대비한 예외 처리
        try:
            df = pd.read_csv(data_path, sep='\t', on_bad_lines='warn')
        except FileNotFoundError:
            print(f"경고: {data_path} 파일을 찾을 수 없습니다. 빈 데이터셋을 반환합니다.")
            self.queries, self.items, self.scores = [], [], []
            return

        self.queries = df['query'].astype(str).tolist()
        self.items = df['item_text'].astype(str).tolist()
        self.scores = df['score'].tolist()

    def __len__(self):
        return len(self.queries)

    def __getitem__(self, idx):
        features = self.tokenizer(
            self.queries[idx], self.items[idx],
            padding='max_length', truncation=True, max_length=self.max_length, return_tensors='pt'
        )
        return {
            'input_ids': features['input_ids'].squeeze(0),
            'attention_mask': features['attention_mask'].squeeze(0),
            'labels': torch.tensor(self.scores[idx], dtype=torch.float)
        }


# 2. 파인튜닝 클래스 (MSELoss 적용) --------------------------------
import random

class CrossEncoderFineTuner:
    def __init__(self, model_name="klue/roberta-base"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = RobertaForSequenceClassification.from_pretrained(model_name, num_labels=1)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.scaler = amp.GradScaler()  # AMP 스케일러 추가
        print(f"✅ 학습을 시작합니다. (사용 디바이스: {self.device})")

    def smooth_labels(self, labels, epsilon=0.02):
        # 라벨을 -epsilon~+epsilon 범위에서 균등 분포로 살짝 흔들기
        noise = (torch.rand_like(labels) * 2 - 1) * epsilon
        smoothed = labels + noise
        # 0~1 범위로 클램프
        return torch.clamp(smoothed, 0.0, 1.0)

    def train(self, train_path, dev_path, output_path, batch_size=32, epochs=5, lr=2e-5, warmup_ratio=0.1, patience=2):
        print("\n--- 데이터 로딩 및 전처리 시작 ---")
        train_set = PointwiseRankingDataset(train_path, self.tokenizer)
        dev_set = PointwiseRankingDataset(dev_path, self.tokenizer)

        train_loader = DataLoader(train_set, batch_size=batch_size, shuffle=True)
        dev_loader = DataLoader(dev_set, batch_size=batch_size * 2)
        print("--- 데이터 로딩 완료 ---\n")

        optimizer = torch.optim.AdamW(self.model.parameters(), lr=lr)
        loss_fn = nn.MSELoss()

        num_training_steps = len(train_loader) * epochs
        num_warmup_steps = int(num_training_steps * warmup_ratio)
        scheduler = get_linear_schedule_with_warmup(
            optimizer, num_warmup_steps=num_warmup_steps, num_training_steps=num_training_steps
        )

        best_score = -1.0
        epochs_no_improve = 0

        for epoch in range(epochs):
            self.model.train()
            total_loss = 0
            progress_bar = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{epochs} (Training)", leave=True)

            for batch in progress_bar:
                optimizer.zero_grad()

                b_input_ids = batch['input_ids'].to(self.device)
                b_attention_mask = batch['attention_mask'].to(self.device)
                b_labels = batch['labels'].to(self.device)

                smoothed_labels = self.smooth_labels(b_labels)  # label smoothing 적용

                with amp.autocast():
                    outputs = self.model(input_ids=b_input_ids, attention_mask=b_attention_mask)
                    loss = loss_fn(outputs.logits.squeeze(), smoothed_labels)

                total_loss += loss.item()

                if torch.isnan(loss):
                    print("🚨 NaN loss 발생! logits:", outputs.logits, "labels:", b_labels)

                self.scaler.scale(loss).backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.scaler.step(optimizer)
                self.scaler.update()
                scheduler.step()

                progress_bar.set_postfix({'loss': loss.item()})

            avg_train_loss = total_loss / len(train_loader)

            # --- 평가 ---
            self.model.eval()
            all_preds, all_labels = [], []
            eval_progress_bar = tqdm(dev_loader, desc=f"Epoch {epoch + 1}/{epochs} (Validation)", leave=True)
            with torch.no_grad():
                for batch in eval_progress_bar:
                    inputs = {k: v.to(self.device) for k, v in batch.items() if k != 'labels'}
                    labels = batch['labels']
                    outputs = self.model(**inputs)
                    all_preds.extend(np.atleast_1d(outputs.logits.squeeze().cpu().numpy()))
                    all_labels.extend(np.atleast_1d(labels.numpy()))

            spearman_corr, _ = spearmanr(all_labels, all_preds)
            print(f"\nEpoch {epoch + 1} 결과 | 훈련 손실: {avg_train_loss:.4f} | 검증 Spearman 상관계수: {spearman_corr:.4f}")

            if spearman_corr > best_score:
                best_score = spearman_corr
                epochs_no_improve = 0
                print(f"✨ 최고 점수 갱신! 모델을 '{output_path}'에 저장합니다. (상관계수: {best_score:.4f})")
                os.makedirs(output_path, exist_ok=True)
                self.model.save_pretrained(output_path)
                self.tokenizer.save_pretrained(output_path)
            else:
                epochs_no_improve += 1
                print(f"성능 향상 없음. ({epochs_no_improve}/{patience})")

            if epochs_no_improve >= patience:
                print(f"\n⚠️ {patience}번의 Epoch 동안 성능 향상이 없어 학습을 조기 종료합니다.")
                break
            print("-" * 70)

        print(f"\n🎉 학습 완료. 최종 최고 점수: {best_score:.4f}")


# 3. 메인 실행 블록 ----------------------------------------
if __name__ == '__main__':
    # --- ⚙️ 학습 설정 ---
    TRAIN_FILE = 'cross_encoder_train_fixed.tsv'
    DEV_FILE = 'cross_encoder_dev_fixed.tsv'
    OUTPUT_MODEL_PATH = './my_best_reranker_mse'  # 모델 저장 경로 변경

    EPOCHS = 10
    # Pointwise 학습은 메모리 효율이 좋으므로 배치 사이즈를 늘릴 수 있습니다.
    BATCH_SIZE = 32
    LEARNING_RATE = 3e-5
    PATIENCE = 3  # 검증 점수가 2번 연속 향상되지 않으면 학습 중단

    # --- 🚀 학습 시작 ---
    print("--- 재랭킹 모델 학습 시작 (MSE Loss) ---")
    print(f"학습 데이터: {TRAIN_FILE}")
    print(f"검증 데이터: {DEV_FILE}")
    print(f"모델 저장 경로: {OUTPUT_MODEL_PATH}")
    print(f"Batch Size: {BATCH_SIZE}, Patience: {PATIENCE}")
    print("-" * 40)

    fine_tuner = CrossEncoderFineTuner()
    fine_tuner.train(
        train_path=TRAIN_FILE,
        dev_path=DEV_FILE,
        output_path=OUTPUT_MODEL_PATH,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        lr=LEARNING_RATE,
        patience=PATIENCE,
    )

# 추론(재랭킹) 클래스 --------------------------


class KCrossEncoderReranker:
    def __init__(self, model_path, device=None, max_length=256, normalize_scores=True):
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.eval()

        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.max_length = max_length
        self.normalize_scores = normalize_scores  # 👉 softmax 정규화 여부

    def rerank(self, query, candidates, top_n=5):
        # 각 후보에 대해 title, overview, intro 결합
        item_texts = [
            f"{item.get('title', '')} {item.get('overview', '')} {item.get('intro', '')}".strip()
            for item in candidates
        ]
        pairs = [(query, text) for text in item_texts]

        # tokenizer로 인코딩
        encodings = self.tokenizer.batch_encode_plus(
            pairs,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt"
        )
        encodings = {k: v.to(self.device) for k, v in encodings.items()}

        # 모델 추론
        with torch.no_grad():
            outputs = self.model(**encodings)
            logits = outputs.logits.squeeze()

            if logits.dim() == 0:  # 입력이 하나일 경우에도 대응
                scores = logits.unsqueeze(0).cpu().numpy()
            else:
                scores = logits.cpu().numpy()

            if self.normalize_scores:
                scores = softmax(torch.tensor(scores), dim=0).numpy()

        sorted_indices = np.argsort(scores)[::-1]
        return [candidates[i] for i in sorted_indices[:top_n]]
