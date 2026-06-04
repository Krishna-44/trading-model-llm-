"""LLM client — LOCAL-FIRST with optional cloud fallbacks.

System provider priority: Ollama (local, free, no billing) → cloud (Anthropic /
OpenAI) → deterministic/keyword fallback in the callers. The trading math NEVER
depends on the LLM: if no provider is reachable, ``generate`` returns None and
callers fall back to a deterministic template.

Hardening: a reused (pooled) HTTP client, optional JSON-constrained output,
temperature / max-tokens controls, one retry, per-call latency logging, and an
Ollama model-existence check that prints a helpful ``ollama pull`` hint.
"""
from __future__ import annotations

import logging
import time

import httpx

from ..config import settings

logger = logging.getLogger("aifos.llm")

# Reused across calls → keep-alive connection pooling (localhost-friendly).
_http = httpx.Client(
    timeout=httpx.Timeout(settings.llm_timeout_s, connect=5.0),
    limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
)
_OLLAMA_GEN_TIMEOUT = 180.0  # local generation (incl. cold model load) can be slow


class LLMClient:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.lower()

    # --- availability / model detection ---------------------------------
    def _ollama_tags(self) -> list[str] | None:
        """Pulled model names, or None if the Ollama server is unreachable."""
        try:
            r = _http.get(f"{settings.ollama_base_url}/api/tags", timeout=3.0)
            r.raise_for_status()
            return [m.get("name", "") for m in r.json().get("models", [])]
        except Exception:  # noqa: BLE001
            return None

    def available(self) -> bool:
        if self.provider == "ollama":
            return self._ollama_tags() is not None
        if self.provider == "anthropic":
            return bool(settings.anthropic_api_key)
        if self.provider == "openai":
            return bool(settings.openai_api_key)
        return False  # "none" or unknown

    def model_present(self, tags: list[str] | None = None) -> bool:
        """For Ollama: is the configured model pulled? Matches the base name too
        (so ``llama3`` satisfies a configured ``llama3:latest`` and vice versa)."""
        if tags is None:
            tags = self._ollama_tags()
        if not tags:
            return False
        want = settings.ollama_model
        base = want.split(":")[0]
        return any(t == want or t.split(":")[0] == base for t in tags)

    # --- generation ------------------------------------------------------
    def generate(self, prompt: str, system: str = "", *, want_json: bool = False,
                 temperature: float = 0.2, max_tokens: int = 600,
                 retries: int = 1, timeout: float | None = None) -> str | None:
        """Return the model's text, or None (→ caller falls back). Never raises.
        ``timeout`` caps each attempt (Ollama); callers on slow hardware pass a
        short value so they fall back quickly instead of hanging."""
        if self.provider == "none":
            return None

        if self.provider == "ollama":  # local readiness checks + helpful hints
            tags = self._ollama_tags()
            if tags is None:
                logger.warning("LLM fallback: Ollama not reachable at %s — start it with "
                               "`ollama serve`.", settings.ollama_base_url)
                return None
            if not self.model_present(tags):
                logger.warning("LLM fallback: Ollama model '%s' not pulled (have: %s). "
                               "Run: ollama pull %s", settings.ollama_model,
                               ", ".join(tags) or "none", settings.ollama_model)
                return None

        label = f"{self.provider}:{settings.ollama_model}" if self.provider == "ollama" else self.provider
        for attempt in range(1, retries + 2):
            t0 = time.monotonic()
            try:
                if self.provider == "ollama":
                    out = self._ollama(prompt, system, want_json, temperature, max_tokens, timeout)
                elif self.provider == "anthropic":
                    out = self._anthropic(prompt, system, temperature, max_tokens)
                elif self.provider == "openai":
                    out = self._openai(prompt, system, want_json, temperature, max_tokens)
                else:
                    return None
                logger.info("LLM %s ok in %.2fs (%d chars)", label,
                            time.monotonic() - t0, len(out or ""))
                return out or None
            except Exception as exc:  # noqa: BLE001 - never let the LLM break a flow
                logger.info("LLM %s attempt %d/%d failed in %.2fs: %s", label, attempt,
                            retries + 1, time.monotonic() - t0, exc)
        return None

    def _ollama(self, prompt: str, system: str, want_json: bool,
                temperature: float, max_tokens: int, timeout: float | None = None) -> str:
        body: dict = {
            "model": settings.ollama_model, "prompt": prompt, "system": system,
            "stream": False, "keep_alive": "5m",
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if want_json:
            body["format"] = "json"  # constrains output to valid JSON
        r = _http.post(f"{settings.ollama_base_url}/api/generate",
                       json=body, timeout=timeout or _OLLAMA_GEN_TIMEOUT)
        r.raise_for_status()
        return (r.json().get("response") or "").strip()

    def _anthropic(self, prompt: str, system: str,
                   temperature: float, max_tokens: int) -> str:
        r = _http.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key,
                     "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-6", "max_tokens": max_tokens,
                  "temperature": temperature, "system": system,
                  "messages": [{"role": "user", "content": prompt}]},
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", [])).strip()

    def _openai(self, prompt: str, system: str, want_json: bool,
                temperature: float, max_tokens: int) -> str:
        body: dict = {"model": "gpt-4o-mini", "max_tokens": max_tokens,
                      "temperature": temperature,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": prompt}]}
        if want_json:
            body["response_format"] = {"type": "json_object"}
        r = _http.post("https://api.openai.com/v1/chat/completions",
                       headers={"Authorization": f"Bearer {settings.openai_api_key}"}, json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
