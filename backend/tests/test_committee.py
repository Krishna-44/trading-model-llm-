import numpy as np
import pandas as pd

from aifos.agents.base import MarketContext
from aifos.agents.committee import AgentCommittee
from aifos.risk import RiskEngine


def _df(n=340, seed=1):
    idx = pd.date_range("2020-01-01", periods=n)
    c = pd.Series(np.cumsum(np.random.default_rng(seed).normal(0, 1, n)) + 400,
                  index=idx).clip(lower=1)
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1e6}, index=idx)
    df.attrs["source"] = "synthetic"
    return df


def _ctx(df):
    # index symbol keeps the test offline (Fundamentals agent abstains, no fetch)
    return MarketContext(symbol="^TESTIDX", asset_class="index", df=df,
                         price=float(df["close"].iloc[-1]), atr=2.0, equity=1_000_000,
                         open_positions=0, exposure_value=0.0, adv_notional=1e7,
                         positions=[], extra={"interval": "1d"})


def test_committee_produces_full_decision():
    d = AgentCommittee().deliberate(_ctx(_df()), RiskEngine())
    assert d.action in ("BUY", "SELL", "HOLD")
    assert len(d.opinions) >= 7
    assert 0.0 <= d.confidence <= 1.0
    assert d.llm_summary  # deterministic fallback always present


def test_offshore_forex_is_vetoed():
    ctx = _ctx(_df())
    ctx.symbol, ctx.asset_class = "EURUSD=X", "forex"
    d = AgentCommittee().deliberate(ctx, RiskEngine())
    assert d.action == "HOLD"
    assert any(o.veto for o in d.opinions)  # compliance FEMA veto


def _news_op(net, impact, stance="neutral"):
    from aifos.agents.base import AgentOpinion
    return AgentOpinion("News Intelligence", stance, 0.5, 0.2, "news", {"net": net, "avg_impact": impact})


def test_news_gate_blocks_long_into_bearish_news():
    blocked, reason = AgentCommittee()._news_gate("long", 0.75, [_news_op(-0.5, 0.6, "bearish")])
    assert blocked and "news gate" in reason.lower()


def test_news_gate_blocks_short_into_bullish_news():
    blocked, _ = AgentCommittee()._news_gate("short", 0.75, [_news_op(0.5, 0.6, "bullish")])
    assert blocked


def test_news_gate_allows_aligned_low_impact():
    blocked, _ = AgentCommittee()._news_gate("long", 0.75, [_news_op(0.4, 0.3, "bullish")])
    assert not blocked


def test_news_gate_holds_on_major_event_low_confidence():
    blocked, _ = AgentCommittee()._news_gate("long", 0.6, [_news_op(0.0, 0.7)])  # conf<0.70 bar
    assert blocked
