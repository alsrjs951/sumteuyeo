from transformers import pipeline

ner_pipeline = pipeline(
    "ner",
    model="vitus9988/klue-roberta-small-ner-identified",
    tokenizer="vitus9988/klue-roberta-small-ner-identified",
    aggregation_strategy="simple"
)

def extract_locations_from_query(query):
    ner_results = ner_pipeline(query)
    # entity_group이 'AD'(주소)인 엔티티만 추출
    return [ent['word'] for ent in ner_results if ent['entity_group'] == "AD"]