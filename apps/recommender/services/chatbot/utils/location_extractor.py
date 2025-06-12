# location_extractor.py

import re
from apps.recommender.services.chatbot.constants import ADMIN_DIVISIONS, LOCATION_ALIASES


class LocationExtractor:
    def __init__(self):
        # ⭐️ [변경점 1] 패턴을 두 종류로 명확히 분리하여 컴파일
        self.specific_name_pattern = self._compile_specific_name_pattern()
        self.generic_address_pattern = re.compile(
            # 'OO시/도 OO구/군' 또는 'OO구/군 OO동' 같은 2단계 주소 형식
            r'(\b\w{2,}[시도군구읍면])\s+(\w{1,}[시군구읍면동])|'
            # 'OO동/로/길' 같은 단일 주소 형식 (숫자 포함 가능)
            r'(\b\w+[\d동로길가])'
        )

    def _compile_specific_name_pattern(self):
        """
        사전에 정의된 모든 지역명과 별칭을 기반으로 정규식 패턴을 생성합니다.
        '남포동에서' 같은 조사를 처리하기 위해 \b(단어경계) 사용법을 수정합니다.
        """
        all_locations = set(LOCATION_ALIASES.keys())
        for province, cities in ADMIN_DIVISIONS.items():
            all_locations.add(province)
            all_locations.update(cities)

        # 길이를 기준으로 내림차순 정렬 (핵심 로직)
        sorted_locations = sorted(list(all_locations), key=len, reverse=True)

        # ⭐️ [변경점 2] 패턴 수정
        # 단어 뒤에 공백, 구두점, 문장의 끝 또는 조사가 오는 경우를 모두 처리
        # (?=...)는 긍정형 전방 탐색(positive lookahead)으로, 조건이 맞는지 확인만 하고 패턴에 포함시키지는 않습니다.
        location_pattern = r'\b(' + '|'.join(
            re.escape(loc) for loc in sorted_locations) + r')(?=[\s,.]|$|은|는|이|가|도|만|의|에|에서|로|과|와|나|랑|까지|부터)'
        return re.compile(location_pattern)

    def extract(self, text: str) -> list[str]:
        """
        개선된 정규식과 후처리 로직으로 텍스트에서 지역명을 추출합니다.
        """
        found_locations = set()

        # 1. 사전에 정의된 특정 지역명 먼저 검색 (가장 정확도가 높음)
        for match in self.specific_name_pattern.finditer(text):
            found_locations.add(match.group(0))

        # 2. 일반적인 주소 형식으로 추가 검색 (사전에 없는 'OO동' 등을 찾기 위함)
        for match in self.generic_address_pattern.finditer(text):
            # 매칭된 전체 문자열을 추가
            found_locations.add(match.group(0).strip())

        # ⭐️ [변경점 3] 더 강력해진 후처리 로직
        if not found_locations:
            return []

        # 문자열을 리스트로 변환하고 원본 텍스트에서의 위치로 정렬
        sorted_found = sorted(list(found_locations), key=lambda x: text.find(x))

        # 포함 관계에 있는 지역명 제거 (예: '해운대구'가 있으면 '해운대'는 제거)
        final_locations = []
        for loc in sorted_found:
            is_substring = False
            for other_loc in sorted_found:
                if loc != other_loc and loc in other_loc:
                    is_substring = True
                    break
            if not is_substring:
                final_locations.append(loc)

        return final_locations
# --- 사용 예시 ---
'''
if __name__ == '__main__':
    extractor = LocationExtractor()

    test_sentences = [
        "부산광역시 사하구 근처 맛집 추천해줘",
        "광안리나 해운대 쪽에 숙소 있어?",
        "경기도 수원시 팔달구 인계동으로 가자",
        "서울 말고 충남 쪽으로 알아봐줘",
        "전북특별자치도 전주시 완산구 효자동",
        "하단에서 서면까지 얼마나 걸려?",
        "강원도 여행 계획 중이야",
        "제주도 말고 제주시에 있는 흑돼지집",
    ]

    for sentence in test_sentences:
        locations = extractor.extract(sentence)
        print(f"입력: {sentence}")
        print(f"추출된 지역명: {locations}\n")
'''