"""Pure-pandas technical indicators — zero native deps (no TA-Lib needed).

Kept deliberately small and well-tested. Each returns a pandas Series/DataFrame
aligned to the input index so they compose cleanly in strategies and agents.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window, min_periods=window).mean()


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def returns(close: pd.Series, log: bool = False) -> pd.Series:
    if log:
        return np.log(close / close.shift(1))
    return close.pct_change()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def bollinger(close: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, window)
    sd = close.rolling(window, min_periods=window).std(ddof=0)
    return pd.DataFrame({"mid": mid, "upper": mid + n_std * sd, "lower": mid - n_std * sd})


def realized_vol(close: pd.Series, window: int = 20, annualize: int = 252) -> pd.Series:
    """Annualized realized volatility from daily returns."""
    r = returns(close)
    return r.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(annualize)


def zscore(s: pd.Series, window: int = 20) -> pd.Series:
    mean = s.rolling(window, min_periods=window).mean()
    sd = s.rolling(window, min_periods=window).std(ddof=0)
    return (s - mean) / sd.replace(0.0, np.nan)
