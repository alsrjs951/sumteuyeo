import faiss
import pickle
from typing import List, Dict
import numpy as np

class FaissManager:
    def __init__(self, index_path: str, id_map_path: str):
        self.index = faiss.read_index(str(index_path))
        # with open(id_map_path, 'rb') as f:
        #     self.id_map = pickle.load(f)
        self.id_map = np.load(id_map_path, allow_pickle=True)
    
    def search(self, query_vec: np.ndarray, top_k: int=30) -> List[int]:
        """정규화된 쿼리 벡터로 FAISS 검색 수행"""
        query_vec = query_vec.astype(np.float32).reshape(1, -1)
        distances, indices = self.index.search(query_vec, top_k)
        return [self.id_map[i] for i in indices[0].tolist()]