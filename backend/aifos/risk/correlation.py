"""Correlation-aware directional concentration check.

The base risk engine sizes and caps each trade independently — so it can't see
that a short BTC and a short ETH are the SAME crypto-short bet held twice, not
two independent edges. This adds the missing portfolio view: it measures
correlation from REAL recent returns and refuses to stack the same directional
bet across correlated assets. Survivability over frequency.
"""
from __future__ import annotations

import numpy as np


def _returns(provider, symbol: str, interval: str, lookback: int) -> np.ndarray:
    df = provider.history(symbol, interval)
    r = df["close"].pct_change().dropna().to_numpy(dtype=float)
    return r[-lookback:] if r.size > lookback else r


def pair_corr(provider, a: str, b: str, *, interval: str = "1d", lookback: int = 90) -> float:
    """Pearson correlation of the two symbols' recent returns (real data).
    Returns 0.0 on any data problem — never raises into the risk gate."""
    if a == b:
        return 1.0
    try:
        ra = _returns(provider, a, interval, lookback)
        rb = _returns(provider, b, interval, lookback)
        n = min(ra.size, rb.size)
        if n < 20:
            return 0.0
        c = float(np.corrcoef(ra[-n:], rb[-n:])[0, 1])
        return c if np.isfinite(c) else 0.0
    except Exception:  # noqa: BLE001 - correlation must never break trading
        return 0.0


def aligned_correlated(provider, cand_symbol: str, cand_dir: int, cand_notional: float,
                       positions: list[dict], *, interval: str = "1d",
                       threshold: float = 0.6, lookback: int = 90) -> tuple[list[dict], float]:
    """Open positions that are correlated (|rho| >= threshold) AND bet the same
    direction as the candidate — i.e. a single factor move hits them together.

    A negatively-correlated position counts as *aligned* when its own direction is
    opposite (short ETH with rho=-0.8 to a long candidate still loads the same
    factor). Returns (aligned_positions, combined_notional).
    """
    aligned: list[dict] = []
    combined = float(cand_notional)
    for p in positions:
        psym = p.get("symbol")
        pdir = int(p.get("dir") or 0)
        pnot = float(p.get("notional") or 0.0)
        if not psym or psym == cand_symbol or pdir == 0 or pnot <= 0:
            continue
        rho = pair_corr(provider, cand_symbol, psym, interval=interval, lookback=lookback)
        if abs(rho) < threshold:
            continue
        if pdir * (1 if rho >= 0 else -1) == cand_dir:  # same directional bet -> stacks
            aligned.append({"symbol": psym, "corr": round(rho, 2),
                            "side": "long" if pdir > 0 else "short",
                            "notional": round(pnot, 0)})
            combined += abs(rho) * pnot
    return aligned, combined
