# 기존 ner.py 또는 새로운 파일
from .location_extractor import LocationExtractor

# LocationExtractor는 내부에 패턴을 컴파일하므로, 초기에 한 번만 생성하는 것이 효율적입니다.
extractor_instance = LocationExtractor()

def extract_locations_from_query(query: str) -> list[str]:
    return extractor_instance.extract(query)
