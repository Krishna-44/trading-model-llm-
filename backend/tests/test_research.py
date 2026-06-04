import numpy as np
import pandas as pd

from aifos.agents.base import MarketContext
from aifos.agents.fundamentals import FundamentalsAgent
from aifos.research.fundamentals import _score, get_fundamentals_client


def test_non_equity_not_applicable():
    # forex/index/crypto have no fundamentals -> not applicable, no network call
    assert get_fundamentals_client().get("USDINR=X").applicable is False
    assert get_fundamentals_client().get("^NSEI").applicable is False


def test_scoring_rewards_quality_and_value():
    f = _score("X.NS", {"pe": 12, "pb": 2.0, "roe": 0.25, "profit_margin": 0.2,
                        "revenue_growth": 0.2, "debt_to_equity": 0.2, "source": "test"})
    assert f.applicable and f.stance == "bullish" and f.composite > 0.62


def test_scoring_penalizes_weak_expensive():
    f = _score("Y.NS", {"pe": 80, "pb": 12, "roe": 0.01, "profit_margin": 0.0,
                        "revenue_growth": -0.1, "debt_to_equity": 3.0, "source": "test"})
    assert f.stance == "bearish"


def test_agent_abstains_on_index():
    idx = pd.date_range("2020-01-01", periods=60)
    c = pd.Series(np.linspace(100, 110, 60), index=idx)
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1e6}, index=idx)
    ctx = MarketContext("^NSEI", "index", df, 110.0, 2.0, 1_000_000,
                        extra={"interval": "1d"})
    op = FundamentalsAgent().analyze(ctx)
    assert op.weight == 0.0  # abstains -> zero impact on the committee
