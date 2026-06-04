from aifos.news.intelligence import _analyze


def test_bullish_headline():
    a = _analyze("Company beats earnings, stock surges to record high")
    assert a["sentiment"] == "bullish" and a["impact_score"] > 0.2 and 0 < a["confidence"] <= 0.8


def test_bearish_headline():
    a = _analyze("Firm misses guidance, faces lawsuit and announces layoffs")
    assert a["sentiment"] == "bearish"


def test_neutral_headline():
    a = _analyze("Company schedules its annual general meeting")
    assert a["sentiment"] == "neutral"


def test_high_impact_macro():
    a = _analyze("Fed signals surprise rate cut amid recession fears")
    assert a["impact_score"] >= 0.5  # macro keywords lift impact
