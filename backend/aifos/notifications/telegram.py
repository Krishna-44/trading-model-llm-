"""Telegram alert notifier for AIFOS.

Sends short messages to your Telegram chat on:
  • Trade open / close (with P&L)
  • Daily-loss kill switch trip
  • Large unrealised loss (configurable threshold)
  • New committee decision (configurable verbosity)

CONFIG (env vars; all optional — telegram silently no-ops if not configured):
  AIFOS_TELEGRAM_BOT_TOKEN   = '1234567890:AAAA...'  # from @BotFather
  AIFOS_TELEGRAM_CHAT_ID     = '123456789'           # see /getUpdates
  AIFOS_TELEGRAM_VERBOSITY   = 'normal'              # quiet | normal | verbose
  AIFOS_TELEGRAM_RATE_LIMIT  = '0.5'                 # min seconds between messages

How to get the token and chat id:
  1. Send /newbot to @BotFather on Telegram, follow prompts, copy the token.
  2. Send any message to your new bot, then visit:
        https://api.telegram.org/bot<TOKEN>/getUpdates
     → look for "chat":{"id":NUMBER,...} — that's your chat id.

Usage in code:
    from aifos.notifications.telegram import get_telegram
    tg = get_telegram()
    tg.send("Hello from AIFOS")
    tg.trade_opened(symbol="RELIANCE.NS", side="long", price=2890.0, size=2, confidence=0.78)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramConfig:
    token: str
    chat_id: str
    verbosity: str = "normal"      # quiet | normal | verbose
    rate_limit_sec: float = 0.5
    base_url: str = "https://api.telegram.org"


class TelegramNotifier:
    """Fire-and-forget notifier. Failures are logged and swallowed."""

    def __init__(self, cfg: TelegramConfig | None = None):
        if cfg is None:
            cfg = _cfg_from_env()
        self.cfg = cfg
        self._enabled = bool(cfg and cfg.token and cfg.chat_id and httpx is not None)
        self._last_sent_ts = 0.0
        if not self._enabled:
            log.info("Telegram disabled (token/chat_id missing or httpx unavailable)")

    # ─── public ─────────────────────────────────────────────────────────
    def send(self, text: str, verbosity_required: str = "normal") -> None:
        """Send a free-form message. verbosity_required is 'quiet' (always),
        'normal' (default), or 'verbose' (only in verbose mode)."""
        if not self._enabled or not self._allows(verbosity_required):
            return
        threading.Thread(target=self._send_now, args=(text,), daemon=True).start()

    def trade_opened(self, symbol: str, side: str, price: float, size: float,
                     confidence: float) -> None:
        self.send(
            f"🟢 *Trade opened* — `{symbol}`\n"
            f"Side: *{side.upper()}*  |  Price: `{price:.2f}`  |  Size: `{size}`\n"
            f"Confidence: `{confidence:.0%}`",
            verbosity_required="normal",
        )

    def trade_closed(self, symbol: str, side: str, entry: float, exit_: float,
                     pnl: float, reason: str = "") -> None:
        emoji = "✅" if pnl >= 0 else "🔴"
        sign = "+" if pnl >= 0 else ""
        self.send(
            f"{emoji} *Trade closed* — `{symbol}`\n"
            f"{side.upper()} {entry:.2f} → {exit_:.2f}  |  P&L: `{sign}{pnl:.2f}`\n"
            f"{reason}".rstrip(),
            verbosity_required="normal",
        )

    def kill_switch_tripped(self, daily_pnl: float, threshold: float) -> None:
        self.send(
            f"🚨 *DAILY LOSS KILL SWITCH TRIPPED* 🚨\n"
            f"Realised P&L today: `{daily_pnl:+.2f}` ≤ threshold `{threshold:+.2f}`.\n"
            f"All new trades blocked until next session.",
            verbosity_required="quiet",  # always send, even on quiet mode
        )

    def unrealised_loss_alert(self, symbol: str, pct_loss: float, value_loss: float) -> None:
        self.send(
            f"⚠️ *Position bleeding* — `{symbol}`\n"
            f"Unrealised: `{pct_loss:+.1%}` ({value_loss:+.2f})",
            verbosity_required="normal",
        )

    def decision(self, symbol: str, action: str, confidence: float, reasoning: str) -> None:
        # Only in verbose mode (one alert per cycle is too noisy otherwise)
        self.send(
            f"🧠 *Committee* — `{symbol}` → *{action}* @ `{confidence:.0%}`\n"
            f"_{reasoning[:300]}_",
            verbosity_required="verbose",
        )

    # ─── internals ──────────────────────────────────────────────────────
    def _allows(self, required: str) -> bool:
        order = {"quiet": 0, "normal": 1, "verbose": 2}
        current = order.get(self.cfg.verbosity, 1)
        needed = order.get(required, 1)
        return current >= needed

    def _send_now(self, text: str) -> None:
        # crude rate limit
        delta = time.monotonic() - self._last_sent_ts
        if delta < self.cfg.rate_limit_sec:
            time.sleep(self.cfg.rate_limit_sec - delta)
        self._last_sent_ts = time.monotonic()
        try:
            url = f"{self.cfg.base_url}/bot{self.cfg.token}/sendMessage"
            r = httpx.post(url, json={
                "chat_id": self.cfg.chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }, timeout=10.0)
            if r.status_code >= 400:
                log.warning("Telegram %s: %s", r.status_code, r.text[:200])
        except Exception as e:  # noqa: BLE001
            log.warning("Telegram send failed (non-fatal): %s", e)


def _cfg_from_env() -> TelegramConfig | None:
    token = os.environ.get("AIFOS_TELEGRAM_BOT_TOKEN", "").strip()
    chat  = os.environ.get("AIFOS_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return None
    return TelegramConfig(
        token=token,
        chat_id=chat,
        verbosity=os.environ.get("AIFOS_TELEGRAM_VERBOSITY", "normal").strip() or "normal",
        rate_limit_sec=float(os.environ.get("AIFOS_TELEGRAM_RATE_LIMIT", "0.5") or 0.5),
    )


_instance: TelegramNotifier | None = None
_lock = threading.Lock()


def get_telegram() -> TelegramNotifier:
    """Singleton accessor — safe to call repeatedly, returns a no-op notifier
    if env vars aren't set."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = TelegramNotifier()
    return _instance


__all__ = ["TelegramNotifier", "TelegramConfig", "get_telegram"]
