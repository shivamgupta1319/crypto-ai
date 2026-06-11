"""Thin, swappable AI provider wrapper (Gemini <-> OpenRouter).

Strictly advisory: this layer only generates *text* (commentary, explanations,
Q&A answers). It never sizes, opens, or closes a trade — the portfolio engine
and broker are the only things that touch positions.

Design:
- No SDK; both providers are plain HTTPS via httpx (keeps deps light + free).
- Graceful when unconfigured: ``complete()`` returns ``None`` (callers fall back
  to non-AI behaviour or show an "AI not configured" hint). Never raises on a
  provider/network error — logs and returns None.
- Keys live in ``.env`` (gitignored). Both providers have free tiers, no card.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

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


def complete(prompt: str, system: str | None = None) -> str | None:
    """Return the model's text for ``prompt``, or ``None`` if unavailable.

    Never raises: a missing key, network error, or malformed response yields None
    so callers degrade gracefully.
    """
    provider = settings.active_ai_provider
    if provider is None:
        return None
    sys_prompt = system or DEFAULT_SYSTEM
    try:
        if provider == "gemini":
            return _gemini(prompt, sys_prompt)
        if provider == "openrouter":
            return _openrouter(prompt, sys_prompt)
    except Exception as exc:  # noqa: BLE001 — advisory layer must not break callers
        logger.warning("AI completion failed (%s): %s", provider, exc)
    return None


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
    resp = httpx.post(
        url,
        params={"key": settings.gemini_api_key},
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
