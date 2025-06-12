import torch
import numpy as np
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from torch.nn.functional import softmax


class KCrossEncoderReranker:
    def __init__(self, model_path, summaries, device=None, max_length=256, normalize_scores=False):
        """
        초기화 메서드 수정:
        - summaries (dict): contentid를 키로, 요약문을 값으로 갖는 딕셔너리를 받습니다.
        """
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.eval()

        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.max_length = max_length
        self.normalize_scores = normalize_scores
        self.summaries = summaries  # ✅ 요약문 딕셔너리를 인스턴스 변수로 저장

    def rerank(self, query, candidates, top_n=5):
        """
        rerank 메서드 수정:
        - item의 title, overview, intro를 결합하는 대신, self.summaries에서 요약문을 조회합니다.
        """
        # ✅ 1. 후보(candidate)들의 contentid를 이용해 요약문을 가져옵니다.
        #    요약문이 없는 경우를 대비해, 요약문이 있는 후보만 필터링합니다.

        valid_candidates = []
        item_texts = []
        for item in candidates:
            content_id = str(item.get("contentid"))
            summary = self.summaries.get(content_id)
            if summary:  # 요약문이 존재하는 경우에만 추가
                valid_candidates.append(item)
                item_texts.append(summary)

        # 요약문을 가진 유효한 후보가 없으면 빈 리스트 반환
        if not valid_candidates:
            return []

        # ✅ 2. (query, 요약문) 쌍을 생성합니다.
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

            if logits.dim() == 0:
                scores = logits.unsqueeze(0).cpu().numpy()
            else:
                scores = logits.cpu().numpy()

            if self.normalize_scores:
                scores = softmax(torch.tensor(scores), dim=0).numpy()

        # 점수 기준으로 정렬 후 top_n개 반환
        sorted_indices = np.argsort(scores)[::-1]

        # ✅ 정렬된 인덱스를 사용해 '요약문이 있던' 후보 리스트(valid_candidates)에서 최종 결과를 선택
        return [valid_candidates[i] for i in sorted_indices[:top_n]]
