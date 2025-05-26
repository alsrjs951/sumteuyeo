from models.embedding import model, faiss_index, spot_data
from services.scoring import score_item

def get_recommendations(query, user_profile, top_n=5):
    query_vec = model.encode([query])
    D, I = faiss_index.search(query_vec, top_n * 5)

    results = []
    for idx_pos, idx in enumerate(I[0]):
        item = spot_data[str(idx)]
        faiss_distance = D[0][idx_pos]
        score = score_item(item, user_profile, faiss_distance)
        results.append((item, score))

    results.sort(key=lambda x: -x[1])
    return [item for item, _ in results[:top_n]]
