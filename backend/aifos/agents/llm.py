"""LLM client. Augments the deterministic quant with natural-language reasoning.

Critically OPTIONAL: if no provider is reachable (e.g. Ollama not running and no
API keys), ``generate`` returns None and callers fall back to a deterministic
template. The trading math never depends on the LLM.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

logger = logging.getLogger("aifos.llm")


class LLMClient:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.lower()

    def available(self) -> bool:
        if self.provider == "none":
            return False
        if self.provider == "ollama":
            try:
                httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
                return True
            except Exception:  # noqa: BLE001
                return False
        if self.provider == "anthropic":
            return bool(settings.anthropic_api_key)
        if self.provider == "openai":
            return bool(settings.openai_api_key)
        return False

    def generate(self, prompt: str, system: str = "") -> str | None:
        try:
            if self.provider == "ollama":
                return self._ollama(prompt, system)
            if self.provider == "anthropic":
                return self._anthropic(prompt, system)
            if self.provider == "openai":
                return self._openai(prompt, system)
        except Exception as exc:  # noqa: BLE001 - never let the LLM break a decision
            logger.info("LLM unavailable (%s): %s", self.provider, exc)
        return None

    def _ollama(self, prompt: str, system: str) -> str | None:
        r = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt,
                  "system": system, "stream": False},
            timeout=settings.llm_timeout_s,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()

    def _anthropic(self, prompt: str, system: str) -> str | None:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key,
                     "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-6", "max_tokens": 400, "system": system,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=settings.llm_timeout_s,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", [])).strip()

    def _openai(self, prompt: str, system: str) -> str | None:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": "gpt-4o-mini", "max_tokens": 400,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}]},
            timeout=settings.llm_timeout_s,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
