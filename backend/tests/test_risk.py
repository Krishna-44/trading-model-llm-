from aifos.config import settings
from aifos.risk import RiskEngine


def test_low_confidence_rejected():
    a = RiskEngine().assess(side="long", entry=100, atr=2, confidence=0.30,
                            equity=1_000_000, open_positions=0, current_exposure_value=0)
    assert not a.approved
    assert any("confidence" in r for r in a.rejections)


def test_high_confidence_sized_with_stops():
    a = RiskEngine().assess(side="long", entry=100, atr=2, confidence=0.85,
                            equity=1_000_000, open_positions=0, current_exposure_value=0)
    assert a.approved
    assert a.size_units > 0
    assert a.stop_loss < 100 < a.take_profit
    assert a.rr_ratio >= settings.min_rr_ratio


def test_position_cap_enforced():
    a = RiskEngine().assess(side="long", entry=100, atr=0.1, confidence=0.9,
                            equity=1_000_000, open_positions=0, current_exposure_value=0)
    # tiny ATR would size huge; must be capped to max_position_pct * equity
    assert a.size_value <= settings.max_position_pct * 1_000_000 + 1


def test_kill_switch_trips_and_blocks():
    e = RiskEngine()
    e.start_new_day(1_000_000)
    e.register_fill(-40_000, 960_000)  # 4% loss > 3% limit
    assert e.kill_switch_active
    a = e.assess(side="long", entry=100, atr=2, confidence=0.95,
                 equity=1_000_000, open_positions=0, current_exposure_value=0)
    assert not a.approved
