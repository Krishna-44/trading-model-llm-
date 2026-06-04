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


def vwap(high: pd.Series, low: pd.Series, close: pd.Series,
         volume: pd.Series, window: int = 20) -> pd.Series:
    """Rolling volume-weighted average price (proxy on bar data)."""
    tp = (high + low + close) / 3.0
    pv = (tp * volume).rolling(window, min_periods=window).sum()
    vv = volume.rolling(window, min_periods=window).sum()
    return pv / vv.replace(0.0, np.nan)


def roc(close: pd.Series, window: int = 12) -> pd.Series:
    return close.pct_change(window) * 100.0


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-balance volume."""
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k: int = 14, d: int = 3) -> pd.DataFrame:
    ll = low.rolling(k, min_periods=k).min()
    hh = high.rolling(k, min_periods=k).max()
    pk = 100.0 * (close - ll) / (hh - ll).replace(0.0, np.nan)
    return pd.DataFrame({"k": pk, "d": pk.rolling(d, min_periods=d).mean()})


def cci(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 20) -> pd.Series:
    tp = (high + low + close) / 3.0
    ma = tp.rolling(window, min_periods=window).mean()
    md = (tp - ma).abs().rolling(window, min_periods=window).mean()
    return (tp - ma) / (0.015 * md.replace(0.0, np.nan))


def mfi(high: pd.Series, low: pd.Series, close: pd.Series,
        volume: pd.Series, window: int = 14) -> pd.Series:
    """Money Flow Index — volume-weighted RSI."""
    tp = (high + low + close) / 3.0
    mf = tp * volume
    pos = mf.where(tp > tp.shift(1), 0.0).rolling(window, min_periods=window).sum()
    neg = mf.where(tp < tp.shift(1), 0.0).rolling(window, min_periods=window).sum()
    mr = pos / neg.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + mr)).fillna(50.0)


def keltner(high: pd.Series, low: pd.Series, close: pd.Series,
            window: int = 20, mult: float = 2.0) -> pd.DataFrame:
    mid = ema(close, window)
    rng = atr(high, low, close, window)
    return pd.DataFrame({"mid": mid, "upper": mid + mult * rng, "lower": mid - mult * rng})


def donchian(high: pd.Series, low: pd.Series, window: int = 20) -> pd.DataFrame:
    upper = high.rolling(window, min_periods=window).max()
    lower = low.rolling(window, min_periods=window).min()
    return pd.DataFrame({"upper": upper, "lower": lower, "mid": (upper + lower) / 2.0})


def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.DataFrame:
    """Average Directional Index + directional indicators (trend strength)."""
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr = atr(high, low, close, window)
    plus_di = 100.0 * plus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / tr.replace(0.0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / tr.replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_line = dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    return pd.DataFrame({"adx": adx_line, "plus_di": plus_di, "minus_di": minus_di})


def supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
               window: int = 10, mult: float = 3.0) -> pd.DataFrame:
    """Supertrend: ATR-banded trend follower. direction +1 = up, -1 = down."""
    atr_v = atr(high, low, close, window)
    hl2 = (high + low) / 2.0
    upper = hl2 + mult * atr_v
    lower = hl2 - mult * atr_v
    fu = np.array(upper, dtype=float)
    fl = np.array(lower, dtype=float)
    cl = np.array(close, dtype=float)
    st = np.full(len(close), np.nan)
    direction = np.ones(len(close))
    for i in range(1, len(close)):
        if np.isnan(atr_v.iloc[i]):
            direction[i] = 1.0
            continue
        fu[i] = upper.iloc[i] if (upper.iloc[i] < fu[i - 1] or cl[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lower.iloc[i] if (lower.iloc[i] > fl[i - 1] or cl[i - 1] < fl[i - 1]) else fl[i - 1]
        if cl[i] > fu[i - 1]:
            direction[i] = 1.0
        elif cl[i] < fl[i - 1]:
            direction[i] = -1.0
        else:
            direction[i] = direction[i - 1]
        st[i] = fl[i] if direction[i] > 0 else fu[i]
    return pd.DataFrame({"supertrend": st, "direction": direction}, index=close.index)
