"""Market Memory — a dependency-free vector store of past market *situations*.

Each memory is a small feature vector (RSI, vol ratio, consensus score, ...)
plus the outcome. At decision time the desk can ask "when conditions looked like
this before, what happened?" This is the honest seed of the RAG/vector-DB layer;
swap in Qdrant/Chroma + real embeddings without changing callers.
"""
from __future__ import annotations

import os
import pickle

import numpy as np

from ..config import settings

_STORE_PATH = os.path.join(settings.data_cache_dir, "market_memory.pkl")


class MarketMemory:
    def __init__(self) -> None:
        self.vectors: list[np.ndarray] = []
        self.meta: list[dict] = []
        self._load()

    def _load(self) -> None:
        if os.path.exists(_STORE_PATH):
            try:
                data = pickle.load(open(_STORE_PATH, "rb"))
                self.vectors, self.meta = data["vectors"], data["meta"]
            except Exception:  # noqa: BLE001
                pass

    def _save(self) -> None:
        os.makedirs(settings.data_cache_dir, exist_ok=True)
        try:
            pickle.dump({"vectors": self.vectors, "meta": self.meta},
                        open(_STORE_PATH, "wb"))
        except Exception:  # noqa: BLE001
            pass

    def add(self, features: list[float], meta: dict) -> None:
        self.vectors.append(np.asarray(features, dtype=float))
        self.meta.append(meta)
        self._save()

    def query(self, features: list[float], k: int = 5) -> list[dict]:
        if not self.vectors:
            return []
        q = np.asarray(features, dtype=float)
        mat = np.vstack(self.vectors)
        # cosine similarity, NaN-safe
        denom = (np.linalg.norm(mat, axis=1) * np.linalg.norm(q)) + 1e-9
        sims = (mat @ q) / denom
        order = np.argsort(-sims)[:k]
        return [{**self.meta[i], "similarity": round(float(sims[i]), 3)} for i in order]

    def stats(self) -> dict:
        return {"count": len(self.vectors)}


_memory: MarketMemory | None = None


def get_memory() -> MarketMemory:
    global _memory
    if _memory is None:
        _memory = MarketMemory()
    return _memory
