from ..utils.embedding import model, faiss_index, get_spot_data
from .scorer import score_item
from asgiref.sync import sync_to_async

spot_data = get_spot_data()

@sync_to_async
def get_recommendations(query, user_profile, top_n=5):
    query_vec = model.encode([query])
    D, I = faiss_index.search(query_vec, top_n * 5)
    scored_results = [
        (spot_data[idx], score_item(spot_data[idx], user_profile)) for idx in I[0]
    ]
    ranked = sorted(scored_results, key=lambda x: -x[1])[:top_n]
    return [item for item, _ in ranked]