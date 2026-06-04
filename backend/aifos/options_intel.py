"""NSE options-chain intelligence — PCR, max pain, OI support/resistance, OI
buildup, IV, and a probabilistic directional bias.

The MATH here is exact and fully implemented now; it runs on any NSE-format
option chain. The live public NSE feed blocks automated access, so without a
real feed (a broker's option-chain API, or a session NSE doesn't block) this
returns ``available: False`` — verified data only, never invented OI.
"""
from __future__ import annotations


def max_pain(strikes: list[dict]) -> float | None:
    """Strike at which total in-the-money option value (writer payout) is minimized."""
    best, best_loss = None, None
    for cand in strikes:
        k = cand["strike"]
        loss = sum(max(0.0, k - s["strike"]) * s["ce_oi"]
                   + max(0.0, s["strike"] - k) * s["pe_oi"] for s in strikes)
        if best_loss is None or loss < best_loss:
            best_loss, best = loss, k
    return best


def analyze_chain(records: dict) -> dict:
    """Compute options intelligence from a parsed NSE `records` object."""
    spot = records.get("underlyingValue")
    expiries = records.get("expiryDates", []) or []
    expiry = expiries[0] if expiries else None
    rows = [d for d in records.get("data", []) if d.get("expiryDate") == expiry]

    strikes: list[dict] = []
    tot_ce_oi = tot_pe_oi = 0
    for d in rows:
        ce, pe = d.get("CE") or {}, d.get("PE") or {}
        ce_oi = ce.get("openInterest", 0) or 0
        pe_oi = pe.get("openInterest", 0) or 0
        tot_ce_oi += ce_oi
        tot_pe_oi += pe_oi
        strikes.append({
            "strike": d.get("strikePrice"),
            "ce_oi": ce_oi, "pe_oi": pe_oi,
            "ce_chg": ce.get("changeinOpenInterest", 0) or 0,
            "pe_chg": pe.get("changeinOpenInterest", 0) or 0,
            "ce_iv": ce.get("impliedVolatility", 0) or 0,
            "pe_iv": pe.get("impliedVolatility", 0) or 0,
            "ce_vol": ce.get("totalTradedVolume", 0) or 0,
            "pe_vol": pe.get("totalTradedVolume", 0) or 0,
        })
    strikes = [s for s in strikes if s["strike"] is not None]
    if not strikes:
        return {"available": False, "reason": "empty option chain"}
    strikes.sort(key=lambda x: x["strike"])

    pcr = round(tot_pe_oi / tot_ce_oi, 3) if tot_ce_oi else 0.0
    mp = max_pain(strikes)
    ivs = [s["ce_iv"] for s in strikes if s["ce_iv"]] + [s["pe_iv"] for s in strikes if s["pe_iv"]]
    avg_iv = round(sum(ivs) / len(ivs), 2) if ivs else 0.0

    # OI walls: heaviest call OI = resistance, heaviest put OI = support
    resistance = sorted(strikes, key=lambda x: x["ce_oi"], reverse=True)[:3]
    support = sorted(strikes, key=lambda x: x["pe_oi"], reverse=True)[:3]
    ce_build = sorted(strikes, key=lambda x: x["ce_chg"], reverse=True)[:3]
    pe_build = sorted(strikes, key=lambda x: x["pe_chg"], reverse=True)[:3]
    unusual = sorted(strikes, key=lambda x: x["ce_vol"] + x["pe_vol"], reverse=True)[:3]

    # inferred (probabilistic) directional bias — NOT a guarantee
    bias, why = "neutral", []
    if pcr >= 1.3:
        bias, t = "bullish", "high PCR (heavy put writing = support)"
        why.append(t)
    elif pcr <= 0.7 and pcr > 0:
        bias, t = "bearish", "low PCR (heavy call writing = resistance)"
        why.append(t)
    pin = None
    if spot and mp:
        drift = (mp / spot - 1) * 100
        pin = round(drift, 2)
        if abs(drift) >= 0.5:
            why.append(f"max-pain pull toward {mp} ({drift:+.1f}% vs spot)")

    return {
        "available": True,
        "spot": spot, "expiry": expiry,
        "pcr": pcr, "bias": bias, "max_pain": mp, "max_pain_vs_spot_pct": pin,
        "avg_iv": avg_iv,
        "support": [{"strike": s["strike"], "pe_oi": s["pe_oi"]} for s in support],
        "resistance": [{"strike": s["strike"], "ce_oi": s["ce_oi"]} for s in resistance],
        "ce_buildup": [{"strike": s["strike"], "chg_oi": s["ce_chg"]} for s in ce_build],
        "pe_buildup": [{"strike": s["strike"], "chg_oi": s["pe_chg"]} for s in pe_build],
        "unusual_activity": [{"strike": s["strike"], "ce_vol": s["ce_vol"], "pe_vol": s["pe_vol"]}
                             for s in unusual],
        "reasoning": "; ".join(why) or "balanced positioning — no clear options edge",
        "note": "Verified NSE OI data; directional bias is an inferred probability, not a guarantee.",
    }


def analyze_options(symbol: str) -> dict:
    """Fetch (real NSE feed) + analyze. Honest `available: False` when no feed."""
    from .data.options import fetch_option_chain, nse_symbol
    nsym, _ = nse_symbol(symbol)
    if not nsym:
        return {"available": False, "symbol": symbol,
                "reason": f"{symbol} has no NSE-listed options"}
    res = fetch_option_chain(symbol)
    if not res.get("available"):
        return {"available": False, "symbol": symbol, "nse_symbol": nsym,
                "reason": res.get("reason", "feed unavailable")}
    out = analyze_chain(res["raw"].get("records", {}))
    out["symbol"] = symbol
    out["nse_symbol"] = nsym
    return out
