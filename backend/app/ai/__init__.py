"""Thin, swappable AI provider wrapper (Gemini <-> OpenRouter).

Strictly advisory: this layer only generates *text* (commentary, explanations,
Q&A answers). It never sizes, opens, or closes a trade — the portfolio engine
and broker are the only things that touch positions.

Design:
- No SDK; both providers are plain HTTPS via httpx (keeps deps light + free).
- Unconfigured: ``complete()`` returns ``None`` (callers show an "add a key" hint).
- Configured but failing: ``complete()`` tries each available provider in turn
  (so a Gemini 429 falls back to OpenRouter when both keys are set) and, if all
  fail, raises ``AIRateLimited`` (HTTP 429) or ``AIError`` so callers can show a
  precise message instead of a generic 502.
- The API key is sent as a header (never in the URL), and failures log only the
  status code — so keys never leak into logs.
- Keys live in ``.env`` (gitignored). Both providers have free tiers, no card.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AIError(Exception):
    """A configured AI provider failed to return a completion."""


class AIRateLimited(AIError):
    """All available AI providers returned 429 (free-tier rate limit)."""

# Default safety/system framing applied to every call unless a caller overrides.
DEFAULT_SYSTEM = (
    "You are a concise, sober crypto market analyst embedded in a personal "
    "paper-trading research tool. You analyse data you are given; you do NOT "
    "place trades or give individualized financial advice. Be brief and factual, "
    "use plain language, and always flag risk and uncertainty (including possible "
    "overfitting) rather than hyping. This is paper trading, not real money."
)


def ai_status() -> dict:
    """What the AI layer can do right now (drives the UI badge)."""
    provider = settings.active_ai_provider
    model = None
    if provider == "gemini":
        model = settings.gemini_model
    elif provider == "openrouter":
        model = settings.openrouter_model
    return {
        "enabled": provider is not None,
        "provider": provider,
        "model": model,
    }


def _provider_order() -> list[str]:
    """Providers to try, in order. In ``auto`` mode both keys give a fallback
    chain (Gemini → OpenRouter); an explicit choice uses only that provider."""
    primary = settings.active_ai_provider
    if primary is None:
        return []
    if (settings.ai_provider or "auto").lower() == "auto":
        order = []
        if settings.gemini_api_key:
            order.append("gemini")
        if settings.openrouter_api_key:
            order.append("openrouter")
        return order
    return [primary]


def complete(prompt: str, system: str | None = None) -> str | None:
    """Return the model's text for ``prompt``.

    - ``None`` when no provider is configured (caller shows an "add a key" hint).
    - Tries each available provider; on a 429 it falls back to the next one.
    - Raises ``AIRateLimited`` / ``AIError`` if every provider fails, so callers
      can surface a precise message.
    """
    order = _provider_order()
    if not order:
        return None
    sys_prompt = system or DEFAULT_SYSTEM
    last_status: int | None = None
    for provider in order:
        try:
            if provider == "gemini":
                return _gemini(prompt, sys_prompt)
            return _openrouter(prompt, sys_prompt)
        except httpx.HTTPStatusError as exc:
            last_status = exc.response.status_code
            logger.warning("AI provider %s failed: HTTP %s", provider, last_status)
        except Exception as exc:  # noqa: BLE001 — log type only, never the key/URL
            logger.warning("AI provider %s failed: %s", provider, type(exc).__name__)
    if last_status == 429:
        raise AIRateLimited(
            "AI rate limit reached (free tier). Wait a minute and try again"
            + (" — or set CRYPTOAI_AI_PROVIDER=openrouter." if settings.openrouter_api_key
               else ".")
        )
    raise AIError("AI request failed. Check the backend logs for details.")


def _gemini(prompt: str, system: str) -> str | None:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": settings.ai_max_output_tokens,
        },
    }
    # Key in a header, NOT the query string, so it can't leak into URLs/logs.
    resp = httpx.post(
        url,
        headers={"x-goog-api-key": settings.gemini_api_key},
        json=body,
        timeout=settings.ai_request_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    return text or None


def _openrouter(prompt: str, system: str) -> str | None:
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "X-Title": "crypto-ai",
        },
        json={
            "model": settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": settings.ai_max_output_tokens,
        },
        timeout=settings.ai_request_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return None
    text = (choices[0].get("message", {}).get("content") or "").strip()
    return text or None
