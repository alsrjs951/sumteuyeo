import faiss
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from asgiref.sync import sync_to_async

model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
faiss_index = faiss.read_index("chatbot/data/spot_index.faiss")
with open("chatbot/data/spot_metadata.json", encoding="utf-8") as f:
    spot_data = json.load(f)

@sync_to_async
def embed_query(query):
    return model.encode([query])

@sync_to_async
def search_faiss(query_vec, top_n):
    return faiss_index.search(query_vec, top_n * 5)

def get_spot_data():
    return spot_data
