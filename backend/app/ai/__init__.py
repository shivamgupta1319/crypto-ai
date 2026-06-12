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


# Cache of auto-discovered free OpenRouter model ids: (fetched_at, [ids]).
_free_models_cache: tuple[float, list[str]] | None = None
_FREE_TTL = 3600.0


def _discover_free_models() -> list[str]:
    """Currently-live ``:free`` chat models from OpenRouter (cached ~1h, best-effort).

    Self-heals the fallback chain as model IDs churn. Returns [] on any failure or
    when autodiscover is disabled."""
    global _free_models_cache
    if not settings.openrouter_autodiscover:
        return []
    import time

    now = time.time()
    if _free_models_cache and (now - _free_models_cache[0]) < _FREE_TTL:
        return _free_models_cache[1]
    ids: list[str] = []
    try:
        resp = httpx.get("https://openrouter.ai/api/v1/models", timeout=10.0)
        resp.raise_for_status()
        for m in resp.json().get("data", []):
            mid = str(m.get("id", ""))
            # text-capable, free; skip obvious non-chat (safety / vision-only) models.
            modality = m.get("architecture", {}).get("modality", "text->text")
            if mid.endswith(":free") and "text" in modality and "safety" not in mid:
                ids.append(mid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenRouter model discovery failed: %s", type(exc).__name__)
    _free_models_cache = (now, ids)
    return ids


def _openrouter_models() -> list[str]:
    """Primary model + curated fallbacks + auto-discovered free models (deduped,
    capped by ``openrouter_max_models``)."""
    out: list[str] = []
    for m in [settings.openrouter_model, *settings.openrouter_fallback_models, *_discover_free_models()]:
        if m and m not in out:
            out.append(m)
        if len(out) >= settings.openrouter_max_models:
            break
    return out


def _attempts() -> list[tuple[str, str]]:
    """Ordered (provider, model) attempts. In ``auto`` mode this is Gemini first,
    then every OpenRouter free model in turn — so a rate-limited model rolls over
    to the next. An explicit ``ai_provider`` restricts to that provider's chain."""
    primary = settings.active_ai_provider
    if primary is None:
        return []
    mode = (settings.ai_provider or "auto").lower()
    attempts: list[tuple[str, str]] = []
    if (mode in ("auto", "gemini")) and settings.gemini_api_key:
        attempts.append(("gemini", settings.gemini_model))
    if (mode in ("auto", "openrouter")) and settings.openrouter_api_key:
        attempts.extend(("openrouter", m) for m in _openrouter_models())
    return attempts


def complete(prompt: str, system: str | None = None) -> str | None:
    """Return the model's text for ``prompt``.

    - ``None`` when no provider is configured (caller shows an "add a key" hint).
    - Tries each (provider, model) in order — Gemini, then each OpenRouter free
      model — rolling past any that 429 / error.
    - Raises ``AIRateLimited`` / ``AIError`` if every attempt fails, so callers
      can surface a precise message.
    """
    attempts = _attempts()
    if not attempts:
        return None
    sys_prompt = system or DEFAULT_SYSTEM
    last_status: int | None = None
    for provider, model in attempts:
        try:
            if provider == "gemini":
                return _gemini(prompt, sys_prompt, model)
            return _openrouter(prompt, sys_prompt, model)
        except httpx.HTTPStatusError as exc:
            last_status = exc.response.status_code
            logger.warning("AI %s/%s failed: HTTP %s", provider, model, last_status)
        except Exception as exc:  # noqa: BLE001 — log type only, never the key/URL
            logger.warning("AI %s/%s failed: %s", provider, model, type(exc).__name__)
    if last_status == 429:
        raise AIRateLimited(
            "All AI models are rate-limited right now (free tiers). "
            "Wait a minute and try again — daily caps reset on the provider's clock."
        )
    raise AIError("AI request failed across all providers. Check the backend logs.")


def _gemini(prompt: str, system: str, model: str | None = None) -> str | None:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model or settings.gemini_model}:generateContent"
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


def _openrouter(prompt: str, system: str, model: str | None = None) -> str | None:
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "X-Title": "crypto-ai",
        },
        json={
            "model": model or settings.openrouter_model,
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
