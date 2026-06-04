import numpy as np

from aifos.news.memory import NewsMemory, _embed


def test_embed_is_unit_normalized():
    v = _embed("Reliance beats earnings, surges to record high")
    assert v.shape == (64,) and abs(np.linalg.norm(v) - 1.0) < 1e-6


def test_embed_empty_is_zero():
    assert np.linalg.norm(_embed("the a an to of")) == 0.0  # all stopwords/short


def test_record_and_similarity():
    m = NewsMemory.__new__(NewsMemory)  # bypass disk load
    m.vectors, m.meta, m._seen = [], [], set()
    m._save = lambda: None  # don't touch disk in tests
    m.record("RELIANCE.NS", "Reliance beats earnings, stock surges", 0, "bullish", 0.6)
    m.record("TCS.NS", "TCS faces lawsuit and announces layoffs", 0, "bearish", 0.5)
    res = m.query("Company beats earnings and surges to a record", k=2)
    assert len(res) >= 1
    assert res[0]["symbol"] == "RELIANCE.NS"  # most similar to the bullish-beats event
    assert res[0]["similarity"] > 0.2


def test_dedup_same_event():
    m = NewsMemory.__new__(NewsMemory)
    m.vectors, m.meta, m._seen = [], [], set()
    m._save = lambda: None
    m.record("X.NS", "same headline", 0, "neutral", 0.2)
    m.record("X.NS", "same headline", 0, "neutral", 0.2)
    assert len(m.vectors) == 1  # deduped by (symbol, title)
