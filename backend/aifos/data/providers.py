"""Market data providers.

``YFinanceProvider`` pulls REAL data for NSE equities, indices, forex and crypto
with no API keys. If the network is unavailable, it degrades gracefully to a
deterministic synthetic series (clearly labelled ``source="synthetic"``) so the
platform always runs and the dashboard always renders.
"""
from __future__ import annotations

import abc
import hashlib
import logging
import math
import os
import pickle
import time

import numpy as np
import pandas as pd

from ..config import settings

logger = logging.getLogger("aifos.data")

# period heuristics per interval so charts/backtests get enough history
_PERIOD_FOR_INTERVAL = {
    "1m": "5d", "5m": "1mo", "15m": "1mo", "30m": "1mo",
    "60m": "3mo", "1h": "3mo", "1d": "3y", "1wk": "5y", "1mo": "10y",
}

OHLCV = ["open", "high", "low", "close", "volume"]


class MarketDataProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def history(self, symbol: str, interval: str = "1d", period: str | None = None) -> pd.DataFrame:
        ...

    def latest_price(self, symbol: str, interval: str = "1d") -> float:
        df = self.history(symbol, interval)
        if df.empty:
            raise ValueError(f"no data for {symbol}")
        return float(df["close"].iloc[-1])


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def __init__(self, cache_ttl_s: int = 900) -> None:
        self.cache_ttl_s = cache_ttl_s
        self._mem: dict[str, tuple[float, pd.DataFrame]] = {}
        os.makedirs(settings.data_cache_dir, exist_ok=True)

    # --- caching ---------------------------------------------------------
    def _cache_path(self, key: str) -> str:
        h = hashlib.sha1(key.encode()).hexdigest()[:16]
        return os.path.join(settings.data_cache_dir, f"bars_{h}.pkl")

    def _read_cache(self, key: str) -> pd.DataFrame | None:
        hit = self._mem.get(key)
        if hit and (time.time() - hit[0]) < self.cache_ttl_s:
            return hit[1]
        path = self._cache_path(key)
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < self.cache_ttl_s:
            try:
                df = pickle.load(open(path, "rb"))
                self._mem[key] = (time.time(), df)
                return df
            except Exception:  # noqa: BLE001 - corrupt cache is non-fatal
                return None
        return None

    def _write_cache(self, key: str, df: pd.DataFrame) -> None:
        self._mem[key] = (time.time(), df)
        try:
            pickle.dump(df, open(self._cache_path(key), "wb"))
        except Exception:  # noqa: BLE001
            pass

    # --- main API --------------------------------------------------------
    def history(self, symbol: str, interval: str = "1d", period: str | None = None) -> pd.DataFrame:
        period = period or _PERIOD_FOR_INTERVAL.get(interval, "3y")
        key = f"{symbol}:{interval}:{period}"
        cached = self._read_cache(key)
        if cached is not None:
            return cached

        df = self._fetch_yf(symbol, interval, period)
        if df is None or df.empty:
            logger.warning("yfinance empty for %s; using synthetic fallback", symbol)
            df = _synthetic_series(symbol, interval)
        self._write_cache(key, df)
        return df

    def _fetch_yf(self, symbol: str, interval: str, period: str) -> pd.DataFrame | None:
        try:
            import yfinance as yf  # imported lazily to keep startup fast

            raw = yf.download(
                symbol, period=period, interval=interval,
                auto_adjust=True, progress=False, threads=False,
            )
            if raw is None or raw.empty:
                return None
            # yfinance may return a column MultiIndex (ticker level) — flatten it.
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw = raw.rename(columns=str.lower)
            cols = [c for c in OHLCV if c in raw.columns]
            df = raw[cols].copy()
            if "volume" not in df.columns:
                df["volume"] = 0.0
            df.index = pd.to_datetime(df.index).tz_localize(None)
            df = df.dropna(subset=["close"])
            df.attrs["source"] = "yfinance"
            return df
        except Exception as exc:  # noqa: BLE001 - network/library issues -> fallback
            logger.warning("yfinance fetch failed for %s: %s", symbol, exc)
            return None


def _synthetic_series(symbol: str, interval: str, n: int = 500) -> pd.DataFrame:
    """Deterministic GBM-ish OHLCV so the platform runs offline.

    Seeded by symbol so a given symbol always renders the same series.
    """
    seed = int(hashlib.sha1(symbol.encode()).hexdigest(), 16) % (2**32)
    rng = np.random.default_rng(seed)
    base = 100 + (seed % 9000)
    drift, vol = 0.0002, 0.012
    rets = rng.normal(drift, vol, n)
    close = base * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, vol / 2, n)))
    low = close * (1 - np.abs(rng.normal(0, vol / 2, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.integers(1e5, 5e6, n).astype(float)
    freq = "D" if interval in ("1d", "1wk", "1mo") else "H"
    idx = pd.date_range(end=pd.Timestamp("2026-06-01"), periods=n, freq=freq)
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
    df.attrs["source"] = "synthetic"
    return df


_provider: MarketDataProvider | None = None


def get_provider() -> MarketDataProvider:
    global _provider
    if _provider is None:
        _provider = YFinanceProvider()
    return _provider
