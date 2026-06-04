"""News historical-similarity memory — extends the market-memory idea to events.

Each analyzed headline is embedded (dependency-free hashing vectorizer, stable
across restarts) and stored. For a new headline we retrieve the most similar
PAST events and, when an event is old enough and tied to a symbol, compute the
REALIZED forward return after it — an honest "what happened last time?" read.
Cold-start: empty; it fills as news is analyzed. No outcomes are invented."""
from __future__ import annotations

import hashlib
import logging
import os
import pickle
import re

import numpy as np

from ..config import settings

logger = logging.getLogger("aifos.news.memory")
_DIM = 64
_MAX = 3000
_STORE = os.path.join(settings.data_cache_dir, "news_memory.pkl")
_STOP = {"the", "a", "an", "to", "of", "in", "on", "and", "for", "is", "as", "at",
         "by", "with", "its", "after", "amid", "over", "from", "into", "this", "that"}


def _embed(title: str) -> np.ndarray:
    v = np.zeros(_DIM)
    for tok in re.findall(r"[a-z]+", title.lower()):
        if len(tok) < 3 or tok in _STOP:
            continue
        # stable hash (NOT Python's salted hash) so embeddings persist across runs
        idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % _DIM
        v[idx] += 1.0
    n = np.linalg.norm(v)
    return v / n if n else v


class NewsMemory:
    def __init__(self) -> None:
        self.vectors: list[np.ndarray] = []
        self.meta: list[dict] = []
        self._seen: set[str] = set()
        self._load()

    def _load(self) -> None:
        if os.path.exists(_STORE):
            try:
                d = pickle.load(open(_STORE, "rb"))
                self.vectors, self.meta = d["vectors"], d["meta"]
                self._seen = {m.get("key", "") for m in self.meta}
            except Exception:  # noqa: BLE001
                pass

    def _save(self) -> None:
        os.makedirs(settings.data_cache_dir, exist_ok=True)
        try:
            pickle.dump({"vectors": self.vectors, "meta": self.meta}, open(_STORE, "wb"))
        except Exception:  # noqa: BLE001
            pass

    def record(self, symbol: str, title: str, ts: int, sentiment: str, impact: float) -> None:
        key = hashlib.md5(f"{symbol}|{title}".encode()).hexdigest()[:16]
        if key in self._seen:
            return
        self._seen.add(key)
        self.vectors.append(_embed(title))
        self.meta.append({"key": key, "symbol": symbol, "title": title, "ts": ts,
                          "sentiment": sentiment, "impact": impact})
        if len(self.vectors) > _MAX:
            self.vectors, self.meta = self.vectors[-_MAX:], self.meta[-_MAX:]
        self._save()

    def query(self, title: str, k: int = 3, exclude_title: str | None = None) -> list[dict]:
        if not self.vectors:
            return []
        q = _embed(title)
        mat = np.vstack(self.vectors)
        denom = (np.linalg.norm(mat, axis=1) * np.linalg.norm(q)) + 1e-9
        sims = (mat @ q) / denom
        order = np.argsort(-sims)
        out = []
        for i in order:
            m = self.meta[i]
            if exclude_title and m["title"] == exclude_title:
                continue
            if sims[i] < 0.2:
                break
            out.append({**m, "similarity": round(float(sims[i]), 3)})
            if len(out) >= k:
                break
        return out

    def stats(self) -> dict:
        return {"events": len(self.vectors)}


_mem: NewsMemory | None = None


def get_news_memory() -> NewsMemory:
    global _mem
    if _mem is None:
        _mem = NewsMemory()
    return _mem


def _forward_return(symbol: str, ts: int, bars: int = 5) -> float | None:
    """Realized return over `bars` bars after the event (None if not resolvable)."""
    if not ts or not symbol:
        return None
    try:
        from datetime import datetime, timezone

        from ..data.providers import get_provider
        df = get_provider().history(symbol, "1d")
        event = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        idx = df.index[df.index >= event]
        if len(idx) == 0:
            return None
        pos = df.index.get_loc(idx[0])
        if pos + bars >= len(df):
            return None
        c = df["close"]
        return round(float(c.iloc[pos + bars] / c.iloc[pos] - 1), 4)
    except Exception:  # noqa: BLE001
        return None


def historical_similarity(symbol: str, title: str, k: int = 3) -> dict:
    matches = get_news_memory().query(title, k=k, exclude_title=title)
    for m in matches:
        m["forward_return_5d"] = _forward_return(m["symbol"], m.get("ts", 0))
    return {"query": title, "matches": matches, "memory": get_news_memory().stats()}
