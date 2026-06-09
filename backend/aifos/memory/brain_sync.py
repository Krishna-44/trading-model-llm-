"""Brain ingestion adapter.

Bridges AIFOS decisions and outcomes into the n8n-based "Corporate Memory Brain"
(see ~/brain-pi-bundle/). Every committee decision becomes a `brain_episodic`
event; outcomes update the corresponding `brain_decisions` row. The brain's
nightly consolidation, forgetting curve, and recall endpoints then become an
out-of-process memory layer for AIFOS — without ever retraining the LLM.

Usage in kernel.py (after decision is made):

    from .memory.brain_sync import get_brain_sync
    brain = get_brain_sync()
    brain.record_decision(decision)
    # ... later, when the trade closes:
    brain.update_outcome(decision, fill, pnl)

All calls are fire-and-forget (best-effort) — the brain being down NEVER
blocks a trade.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover - httpx already in requirements
    httpx = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

BRAIN_URL_DEFAULT = "http://pi5.local:5678"
_DEFAULT_TIMEOUT = 5.0


@dataclass(frozen=True)
class BrainConfig:
    base_url: str
    ingest_path: str = "/webhook/brain-ingest"
    recall_path: str = "/webhook/brain-recall-lite"
    timeout: float = _DEFAULT_TIMEOUT
    auth_header: str | None = None
    auth_value: str | None = None


def _cfg_from_env() -> BrainConfig:
    return BrainConfig(
        base_url=os.environ.get("AIFOS_BRAIN_URL", BRAIN_URL_DEFAULT).rstrip("/"),
        ingest_path=os.environ.get("AIFOS_BRAIN_INGEST_PATH", "/webhook/brain-ingest"),
        recall_path=os.environ.get("AIFOS_BRAIN_RECALL_PATH", "/webhook/brain-recall-lite"),
        timeout=float(os.environ.get("AIFOS_BRAIN_TIMEOUT", _DEFAULT_TIMEOUT)),
        auth_header=os.environ.get("AIFOS_BRAIN_AUTH_HEADER") or None,
        auth_value=os.environ.get("AIFOS_BRAIN_AUTH_VALUE") or None,
    )


class BrainSync:
    """Best-effort, fire-and-forget brain client. Never raises into AIFOS."""

    def __init__(self, cfg: BrainConfig | None = None):
        self.cfg = cfg or _cfg_from_env()
        self._enabled = httpx is not None and bool(self.cfg.base_url)
        if not self._enabled:
            log.info("BrainSync disabled (httpx missing or no AIFOS_BRAIN_URL)")

    # ─── public ─────────────────────────────────────────────────────────
    def record_decision(self, decision: Any) -> None:
        """Send a committee decision into brain_episodic as event_type='decision'."""
        if not self._enabled:
            return
        payload = self._decision_payload(decision)
        threading.Thread(target=self._post, args=(self.cfg.ingest_path, payload),
                         daemon=True).start()

    def update_outcome(self, decision: Any, fill: dict, pnl: float) -> None:
        """Send an outcome event tied back to the original decision by symbol+ts."""
        if not self._enabled:
            return
        payload = self._outcome_payload(decision, fill, pnl)
        threading.Thread(target=self._post, args=(self.cfg.ingest_path, payload),
                         daemon=True).start()

    def recall_similar(self, symbol: str, question: str, limit: int = 5) -> list[dict]:
        """Query the brain for prior similar situations. SYNCHRONOUS — used at
        decision time. Returns [] on any failure."""
        if not self._enabled:
            return []
        try:
            url = self.cfg.base_url + self.cfg.recall_path
            headers = self._headers()
            r = httpx.post(url, json={
                "question": question, "subject": symbol, "limit": limit,
            }, headers=headers, timeout=self.cfg.timeout)
            r.raise_for_status()
            data = r.json()
            return data.get("results", []) if isinstance(data, dict) else []
        except Exception as e:  # noqa: BLE001
            log.warning("brain recall failed: %s", e)
            return []

    # ─── internals ──────────────────────────────────────────────────────
    def _decision_payload(self, decision: Any) -> dict:
        symbol = getattr(decision, "symbol", "?")
        action = getattr(decision, "action", "HOLD")
        confidence = float(getattr(decision, "confidence", 0.0) or 0.0)
        reasoning = getattr(decision, "reasoning", "")
        opinions = getattr(decision, "opinions", []) or []
        return {
            "subject": str(symbol),
            "raw_text": (
                f"AIFOS committee decided {action} on {symbol} with "
                f"confidence {confidence:.2f}. {reasoning}"
            ),
            "importance": float(min(1.0, max(0.0, confidence))),
            "event_type": "decision",
            "source": "aifos",
            "metadata": {
                "symbol": symbol, "action": action, "confidence": confidence,
                "opinions": [
                    {"agent": getattr(o, "agent", "?"),
                     "stance": getattr(o, "stance", "?"),
                     "confidence": float(getattr(o, "confidence", 0.0) or 0.0)}
                    for o in opinions
                ],
                "decision_id": _decision_id(decision),
            },
        }

    def _outcome_payload(self, decision: Any, fill: dict, pnl: float) -> dict:
        symbol = getattr(decision, "symbol", "?")
        return {
            "subject": str(symbol),
            "raw_text": (
                f"AIFOS trade on {symbol} closed. P&L {pnl:+.2f} INR. "
                f"Fill: {fill}."
            ),
            "importance": float(min(1.0, abs(pnl) / 10000.0 + 0.3)),
            "event_type": "outcome",
            "source": "aifos",
            "metadata": {
                "decision_id": _decision_id(decision),
                "symbol": symbol, "pnl": pnl, "fill": fill,
            },
        }

    def _post(self, path: str, payload: dict) -> None:
        try:
            url = self.cfg.base_url + path
            r = httpx.post(url, json=payload, headers=self._headers(),
                           timeout=self.cfg.timeout)
            if r.status_code >= 400:
                log.warning("brain ingest HTTP %s: %s", r.status_code, r.text[:200])
        except Exception as e:  # noqa: BLE001
            log.warning("brain ingest failed (non-fatal): %s", e)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.cfg.auth_header and self.cfg.auth_value:
            h[self.cfg.auth_header] = self.cfg.auth_value
        return h


def _decision_id(decision: Any) -> str:
    """Stable id for matching decision→outcome later. Uses symbol+timestamp."""
    sym = getattr(decision, "symbol", "?")
    ts  = getattr(decision, "ts", None) or getattr(decision, "timestamp", None)
    return f"aifos:{sym}:{ts}"


_instance: BrainSync | None = None
_lock = threading.Lock()


def get_brain_sync() -> BrainSync:
    """Singleton accessor."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = BrainSync()
    return _instance


__all__ = ["BrainSync", "BrainConfig", "get_brain_sync"]
