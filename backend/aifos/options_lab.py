"""Paper options lab — practise option strategies with virtual money.

Honest by construction: there is no live NSE option-chain feed, so premiums are
MODEL-priced with Black–Scholes from the underlying's spot + its realised
volatility (used as an IV proxy). Clearly a simulation for learning — not live
market quotes, and no guarantee real fills would match.
"""
from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()
RATE = 0.065  # ~India risk-free proxy

STRATEGIES = {
    "long_straddle":    {"label": "Long Straddle",    "bias": "volatile",
                         "desc": "Buy ATM Call + ATM Put — profit from a big move EITHER way (long volatility). Loses if price sits still (theta)."},
    "long_strangle":    {"label": "Long Strangle",    "bias": "volatile",
                         "desc": "Buy OTM Call + OTM Put — cheaper than a straddle, but needs a bigger move to pay off."},
    "bull_call_spread": {"label": "Bull Call Spread", "bias": "bullish",
                         "desc": "Buy ATM Call, sell a higher Call — limited-risk, limited-reward bullish bet."},
    "bear_put_spread":  {"label": "Bear Put Spread",  "bias": "bearish",
                         "desc": "Buy ATM Put, sell a lower Put — limited-risk, limited-reward bearish bet."},
    "iron_condor":      {"label": "Iron Condor",      "bias": "range",
                         "desc": "Sell OTM Call+Put, buy further-OTM wings — profit if price stays in a RANGE (short volatility)."},
}

LOT_SIZE = {"^NSEI": 75, "^NSEBANK": 35}


def lot_size(symbol: str) -> int:
    return LOT_SIZE.get(symbol, 1)


def strike_step(spot: float) -> float:
    if spot >= 20000:
        return 100.0
    if spot >= 5000:
        return 50.0
    if spot >= 1000:
        return 20.0
    if spot >= 200:
        return 5.0
    if spot >= 50:
        return 2.5
    return 1.0


def black_scholes(spot: float, strike: float, t: float, vol: float, kind: str, rate: float = RATE) -> dict:
    """European option premium + greeks. kind: 'CE' (call) | 'PE' (put). t in years."""
    if t <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        intrinsic = max(0.0, spot - strike) if kind == "CE" else max(0.0, strike - spot)
        return {"premium": round(intrinsic, 2), "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    srt = vol * math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * t) / srt
    d2 = d1 - srt
    disc = math.exp(-rate * t)
    pdf = _N.pdf(d1)
    if kind == "CE":
        premium = spot * _N.cdf(d1) - strike * disc * _N.cdf(d2)
        delta = _N.cdf(d1)
        theta = -(spot * pdf * vol) / (2 * math.sqrt(t)) - rate * strike * disc * _N.cdf(d2)
    else:
        premium = strike * disc * _N.cdf(-d2) - spot * _N.cdf(-d1)
        delta = _N.cdf(d1) - 1.0
        theta = -(spot * pdf * vol) / (2 * math.sqrt(t)) + rate * strike * disc * _N.cdf(-d2)
    return {"premium": round(max(premium, 0.0), 2), "delta": round(delta, 3),
            "gamma": round(pdf / (spot * srt), 6), "theta": round(theta / 365.0, 2),
            "vega": round(spot * pdf * math.sqrt(t) / 100.0, 2)}


def _sign(side: str) -> int:
    return 1 if side == "buy" else -1


def net_value(legs: list[dict], spot: float, t: float, vol: float) -> float:
    """Signed mark-to-model value of the leg set (long = +premium, short = -premium)."""
    total = 0.0
    for lg in legs:
        prem = black_scholes(spot, lg["strike"], t, vol, lg["kind"])["premium"]
        total += _sign(lg["side"]) * prem * lg["qty"]
    return round(total, 2)


def _analyze(legs: list[dict], spot: float) -> dict:
    """Expiry payoff scan → max profit/loss + breakevens (±40% of spot)."""
    def payoff(s: float) -> float:
        tot = 0.0
        for lg in legs:
            intrinsic = max(0.0, s - lg["strike"]) if lg["kind"] == "CE" else max(0.0, lg["strike"] - s)
            tot += _sign(lg["side"]) * (intrinsic - lg["premium"]) * lg["qty"]
        return tot
    lo, hi, n = spot * 0.6, spot * 1.4, 400
    xs = [lo + (hi - lo) * i / n for i in range(n + 1)]
    ys = [payoff(x) for x in xs]
    bes = []
    for i in range(1, len(xs)):
        if (ys[i - 1] <= 0 <= ys[i] or ys[i - 1] >= 0 >= ys[i]) and ys[i] != ys[i - 1]:
            bes.append(round(xs[i - 1] + (xs[i] - xs[i - 1]) * (-ys[i - 1]) / (ys[i] - ys[i - 1]), 2))
    np_ = sum(_sign(lg["side"]) * lg["premium"] * lg["qty"] for lg in legs)
    # "unlimited" only if the payoff is still RISING at an edge (long call/put/straddle);
    # spreads & condors PLATEAU at the edge, so their max is the capped peak.
    unlimited = (ys[-1] > ys[-2] + 0.01) or (ys[0] > ys[1] + 0.01)
    return {
        "net_premium": round(np_, 2),
        "flow": "debit (you pay)" if np_ > 0 else "credit (you receive)",
        "max_profit": ("unlimited" if unlimited else round(max(ys), 2)),
        "max_loss": round(min(ys), 2),
        "breakevens": sorted(set(bes)),
        "payoff": [{"s": round(xs[i], 0), "p": round(ys[i], 0)} for i in range(0, len(xs), n // 32)],
    }


def build_strategy(name: str, symbol: str, spot: float, vol: float, days: int, lots: int = 1) -> dict:
    if name not in STRATEGIES:
        raise ValueError(f"unknown strategy '{name}'")
    t = max(days, 1) / 365.0
    step = strike_step(spot)
    atm = round(spot / step) * step
    qty = max(1, lots) * lot_size(symbol)

    def leg(kind: str, strike: float, side: str) -> dict:
        g = black_scholes(spot, strike, t, vol, kind)
        return {"kind": kind, "strike": round(strike, 2), "side": side,
                "premium": g["premium"], "delta": g["delta"], "theta": g["theta"], "qty": qty}

    builders = {
        "long_straddle":    lambda: [leg("CE", atm, "buy"), leg("PE", atm, "buy")],
        "long_strangle":    lambda: [leg("CE", atm + step, "buy"), leg("PE", atm - step, "buy")],
        "bull_call_spread": lambda: [leg("CE", atm, "buy"), leg("CE", atm + 2 * step, "sell")],
        "bear_put_spread":  lambda: [leg("PE", atm, "buy"), leg("PE", atm - 2 * step, "sell")],
        "iron_condor":      lambda: [leg("CE", atm + step, "sell"), leg("CE", atm + 3 * step, "buy"),
                                     leg("PE", atm - step, "sell"), leg("PE", atm - 3 * step, "buy")],
    }
    legs = builders[name]()
    info = STRATEGIES[name]
    return {"strategy": name, "label": info["label"], "bias": info["bias"], "desc": info["desc"],
            "symbol": symbol, "spot": round(spot, 2), "atm_strike": atm, "expiry_days": days,
            "vol_used": round(vol, 3), "lots": max(1, lots), "lot_size": lot_size(symbol),
            "legs": legs, **_analyze(legs, spot),
            "note": "Black–Scholes model prices (IV proxied by realised vol). Paper simulation, not live quotes."}
