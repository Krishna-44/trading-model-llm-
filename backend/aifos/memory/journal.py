"""Self-Evaluation Engine (the seed of the learning loop).

Records what the committee predicted vs. what the market did, then mines simple,
honest lessons from the trade history. This is intentionally transparent rather
than a black box — every "lesson" is a verifiable aggregate, not a vibe."""
from __future__ import annotations

from ..persistence.repo import Repository


class SelfEvaluator:
    def __init__(self, repo: Repository | None = None) -> None:
        self.repo = repo or Repository()

    def journal_decision(self, decision, fill) -> int:
        """Seed a journal entry at execution time (outcome resolved later)."""
        predicted = {
            "side": decision.side, "confidence": decision.confidence,
            "stop_loss": decision.sizing.get("stop_loss"),
            "take_profit": decision.sizing.get("take_profit"),
            "rr_ratio": decision.sizing.get("rr_ratio"),
        }
        actual = {"entry": fill.price, "ts": fill.ts} if fill else {}
        return self.repo.save_journal(
            symbol=decision.symbol, predicted=predicted, actual=actual,
            outcome="open", lesson="",
        )

    def mine_lessons(self) -> list[str]:
        """Aggregate honest lessons from realized trades."""
        trades = self.repo.recent_trades(500)
        closed = [t for t in trades if t.get("realized_pnl", 0.0) != 0.0]
        lessons: list[str] = []
        if len(closed) < 3:
            return ["Not enough closed trades yet — the desk is still observing. "
                    "It will only report patterns once it has a real sample."]

        wins = [t for t in closed if t["realized_pnl"] > 0]
        win_rate = len(wins) / len(closed)
        avg_win = sum(t["realized_pnl"] for t in wins) / max(1, len(wins))
        losers = [t for t in closed if t["realized_pnl"] <= 0]
        avg_loss = sum(t["realized_pnl"] for t in losers) / max(1, len(losers))
        lessons.append(
            f"Across {len(closed)} closed trades: win rate {win_rate:.0%}, "
            f"avg win {avg_win:,.0f} vs avg loss {avg_loss:,.0f}."
        )
        # side asymmetry
        for side in ("buy", "sell"):
            s = [t for t in closed if t["side"] == side]
            if len(s) >= 3:
                wr = sum(1 for t in s if t["realized_pnl"] > 0) / len(s)
                lessons.append(f"{side.upper()} trades: {wr:.0%} win rate over {len(s)} samples.")
        if avg_loss != 0 and abs(avg_win / avg_loss) < 1.5:
            lessons.append("Reward:risk realized is below target — tighten entries or "
                           "let winners run longer before the next live step.")
        return lessons
