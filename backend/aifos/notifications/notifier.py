"""External alerts — Telegram + Discord webhooks.

Best-effort and fully optional: if no channels are configured it no-ops, so the
core runs unchanged. Fired on the events that actually matter for capital safety
(kill-switch trips, daily-loss breaches, fills). Email/SMS are intentionally left
as a provider-backed extension."""
from __future__ import annotations

import logging

import httpx

from ..config import settings

logger = logging.getLogger("aifos.alerts")
_EMOJI = {"info": "ℹ️", "warn": "⚠️", "critical": "🚨"}


class Notifier:
    def channels(self) -> list[str]:
        ch = []
        if settings.telegram_bot_token and settings.telegram_chat_id:
            ch.append("telegram")
        if settings.discord_webhook_url:
            ch.append("discord")
        return ch

    def send(self, title: str, message: str, level: str = "info") -> dict:
        if not settings.alerts_enabled:
            return {"sent": [], "reason": "alerts disabled"}
        text = f"{_EMOJI.get(level, '')} AIFOS — {title}\n{message}"
        sent = []
        for c in self.channels():
            try:
                (self._telegram if c == "telegram" else self._discord)(text)
                sent.append(c)
            except Exception as exc:  # noqa: BLE001 - alerts must never break trading
                logger.info("alert via %s failed: %s", c, exc)
        return {"sent": sent, "channels": self.channels()}

    def _telegram(self, text: str) -> None:
        httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text}, timeout=8,
        ).raise_for_status()

    def _discord(self, text: str) -> None:
        httpx.post(settings.discord_webhook_url, json={"content": text}, timeout=8).raise_for_status()


_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier
