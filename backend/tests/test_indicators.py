import numpy as np
import pandas as pd

from aifos.indicators import atr, rsi, sma


def _ramp(n=80):
    return pd.Series(np.linspace(100, 120, n))


def test_rsi_in_bounds():
    r = rsi(_ramp())
    assert r.dropna().between(0, 100).all()


def test_sma_value():
    assert sma(pd.Series([1, 2, 3, 4]), 2).iloc[-1] == 3.5


def test_atr_non_negative():
    n = 80
    base = np.arange(n) + 100.0
    df = pd.DataFrame({"high": base + 1, "low": base - 1, "close": base})
    assert atr(df["high"], df["low"], df["close"]).dropna().ge(0).all()
