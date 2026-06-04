import numpy as np
import pandas as pd

from aifos.risk.correlation import aligned_correlated, pair_corr


class _Prov:
    """Stub provider: BTC and ETH share a driver (highly correlated), gold is independent."""
    def __init__(self) -> None:
        rng = np.random.default_rng(0)
        driver = np.cumsum(rng.normal(0, 1, 200))
        self._series = {
            "BTC-USD": 100 + driver + rng.normal(0, 0.15, 200),
            "ETH-USD": 100 + driver + rng.normal(0, 0.15, 200),
            "GOLD": 100 + np.cumsum(rng.normal(0, 1, 200)),
        }

    def history(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        c = pd.Series(self._series[symbol]).clip(lower=1)
        return pd.DataFrame({"close": c.values}, index=pd.date_range("2020-01-01", periods=len(c)))


def test_pair_corr_distinguishes_correlated_from_independent():
    p = _Prov()
    assert pair_corr(p, "BTC-USD", "ETH-USD") > 0.6
    assert abs(pair_corr(p, "BTC-USD", "GOLD")) < 0.6


def test_aligned_flags_stacked_same_direction():
    p = _Prov()
    short_eth = [{"symbol": "ETH-USD", "dir": -1, "notional": 40000}]
    # candidate SHORT BTC while already SHORT ETH -> stacked same crypto-short bet
    aligned, combined = aligned_correlated(p, "BTC-USD", -1, 40000, short_eth)
    assert [a["symbol"] for a in aligned] == ["ETH-USD"]
    assert combined > 40000


def test_opposite_direction_is_not_flagged():
    p = _Prov()
    short_eth = [{"symbol": "ETH-USD", "dir": -1, "notional": 40000}]
    # candidate LONG BTC vs SHORT ETH (positively correlated) -> opposite bet, a hedge
    aligned, _ = aligned_correlated(p, "BTC-USD", 1, 40000, short_eth)
    assert aligned == []


def test_independent_asset_is_not_flagged():
    p = _Prov()
    short_gold = [{"symbol": "GOLD", "dir": -1, "notional": 40000}]
    aligned, _ = aligned_correlated(p, "BTC-USD", -1, 40000, short_gold)
    assert aligned == []
