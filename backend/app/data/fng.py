"""Fear & Greed Index client (alternative.me, free, no API key)."""
from __future__ import annotations

import httpx

from app.config import settings


def get_fear_greed() -> dict:
    """Return the latest Fear & Greed reading plus a short history.

    Shape: {"value": int, "classification": str, "history": [{value, classification, ts}]}.
    Returns a safe fallback dict on network error so the dashboard never breaks.
    """
    try:
        resp = httpx.get(settings.fng_url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except (httpx.HTTPError, ValueError):
        return {"value": None, "classification": "unavailable", "history": []}

    if not data:
        return {"value": None, "classification": "unavailable", "history": []}

    history = [
        {
            "value": int(d["value"]),
            "classification": d["value_classification"],
            "ts": int(d["timestamp"]),
        }
        for d in data
    ]
    latest = history[0]
    return {
        "value": latest["value"],
        "classification": latest["classification"],
        "history": history,
    }
