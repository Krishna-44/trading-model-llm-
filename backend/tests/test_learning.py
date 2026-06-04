from aifos.learning.video import _heuristic_extract, _video_id


def test_video_id_parsing():
    assert _video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _video_id("not a url") is None


def test_heuristic_extraction():
    t = ("We use the RSI and a 200 EMA. Enter on a breakout. Always set a stop loss "
         "with a 2:1 risk reward. Take profit near resistance.")
    s = _heuristic_extract(t)
    assert "rsi" in s["indicators"] and "ema" in s["indicators"]
    assert s["uses_stop_loss"] is True
    assert "breakout" in s["entry_rules"]
    assert s["method"] == "heuristic"
