def get_user_profile(user_id):
    # DB 연동 혹은 세션 기반 추후 확장 가능
    return {
        "lcls3": ["한식", "자연경관"],
        "visited": ["서울타워"],
        "location": "서울",
        "preferred_regions": ["서울", "경기도"]
    }
