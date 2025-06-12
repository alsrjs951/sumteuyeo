def get_user_profile(user_id):
    # DB 연동 혹은 세션 기반 추후 확장 가능
    return {
        "liked_lcls": [""],
        "visited": [""],
        "location": "부산",
        "preferred_regions": ["부산"]
    }
