from aifos.assistant.brain import _affected, _control, _detect_symbol, _route


class _FakeRepo:
    def recent_decisions(self, n=6):
        return []


class _FakeKernel:
    def __init__(self):
        self.killed = self.resumed = self.swept = False
        self.auto = None
        self.repo = _FakeRepo()

    def portfolio(self):
        return {"account": {"equity": 1_000_000, "cash": 1_000_000, "currency": "INR",
                            "realized_pnl": 0}, "positions": [], "open_positions": 0,
                "unrealized_pnl": 0, "mode": "paper", "broker": "paper"}

    def risk_snapshot(self):
        return {"kill_switch_active": False, "daily_pnl": 0, "daily_loss_limit": -30000,
                "daily_loss_used_pct": 0.0, "limits": {"confidence_threshold": 0.62,
                "max_open_positions": 5, "min_rr_ratio": 1.5}}

    def kill(self, reason=""):
        self.killed = True

    def resume(self):
        self.resumed = True

    def set_autonomous(self, on):
        self.auto = on

    def run_universe(self, execute=True):
        self.swept = True
        return [{"symbol": "X.NS", "action": "HOLD"}]


def test_detect_symbol():
    assert _detect_symbol("what about reliance", ["RELIANCE.NS"]) == "RELIANCE.NS"
    assert _detect_symbol("how is nifty", ["^NSEI"]) == "^NSEI"


def test_affected_company_and_macro():
    aff, macro = _affected("Reliance hands over documents in probe", ["RELIANCE.NS", "TCS.NS"])
    assert "RELIANCE.NS" in aff and not macro
    _, macro2 = _affected("RBI signals a surprise rate cut", ["RELIANCE.NS"])
    assert macro2


def test_control_kill_resume_scan():
    k = _FakeKernel()
    assert "halt" in _control(k, "stop trading now").lower() and k.killed
    k2 = _FakeKernel()
    _control(k2, "resume trading")
    assert k2.resumed
    k3 = _FakeKernel()
    assert "swept" in _control(k3, "scan the market").lower() and k3.swept


def test_control_returns_none_for_questions():
    assert _control(_FakeKernel(), "what is my portfolio") is None


def test_route_portfolio_and_risk():
    assert "Equity" in _route(_FakeKernel(), "what is my portfolio", None)
    assert "kill switch" in _route(_FakeKernel(), "how is my risk", None).lower()
