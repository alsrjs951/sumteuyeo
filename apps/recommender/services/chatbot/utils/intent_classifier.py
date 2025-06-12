from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# 저장된 모델 경로 (fine_tune.py에서 저장한 곳과 같아야 함)
MODEL_DIR = r'C:/Users/User/Desktop/django/sumteuyeo/apps/recommender/services/chatbot/utils/ml/saved_kcelectra_intent'

# 토크나이저와 모델 로드
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)

# 모델을 평가 모드로 전환
model.eval()


def predict_intent_transformer(text: str) -> str:
    # 입력 문장 토크나이즈
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True)

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    predicted_class_id = torch.argmax(logits, dim=1).item()
    # 예측된 레이블 반환
    return model.config.id2label[predicted_class_id]

# label2id = {
#     'recommend_activity': 0,
#     'recommend_food': 1,
#     'recommend_history': 2,
#     'recommend_leisure': 3,
#     'recommend_nature': 4,
#     'recommend_quite': 5,
#     'recommend_shopping': 6,
#     'recommend_tour': 7
# }