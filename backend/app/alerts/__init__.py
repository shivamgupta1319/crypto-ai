"""Free alerting — Telegram bot + Discord webhook. No paid service, no card.

Configure via env (gitignored): CRYPTOAI_TELEGRAM_BOT_TOKEN + CRYPTOAI_TELEGRAM_CHAT_ID
and/or CRYPTOAI_DISCORD_WEBHOOK_URL. All sends are best-effort and never raise into
the caller (a failed alert must not break a scan cycle).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("cryptoai.alerts")


def _send_telegram(text: str) -> bool:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        r = httpx.post(url, json={
            "chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10.0)
        return r.status_code == 200
    except httpx.HTTPError:
        logger.warning("telegram alert failed", exc_info=True)
        return False


def _send_discord(text: str) -> bool:
    if not settings.discord_webhook_url:
        return False
    try:
        r = httpx.post(settings.discord_webhook_url, json={"content": text}, timeout=10.0)
        return r.status_code in (200, 204)
    except httpx.HTTPError:
        logger.warning("discord alert failed", exc_info=True)
        return False


def send_alert(text: str) -> bool:
    """Send to every configured channel. Returns True if at least one succeeded."""
    if not settings.alerts_enabled:
        return False
    sent = False
    sent |= _send_telegram(text)
    sent |= _send_discord(text)
    return sent


def _emoji(direction: str) -> str:
    return "🟢" if direction == "LONG" else "🔴"


def alert_signal(s: dict[str, Any]) -> None:
    send_alert(
        f"{_emoji(s['direction'])} <b>SIGNAL</b> {s['symbol']} {s['timeframe']} · {s['strategy']}\n"
        f"{s['direction']} @ {s['entry']} | stop {s['stop']} | target {s['target']} "
        f"| R:R {s.get('rr', '?')} | conf {round(s['confidence'] * 100)}%"
    )


def alert_trade_opened(ev: dict[str, Any]) -> None:
    send_alert(
        f"📈 <b>OPENED</b> {ev['symbol']} {ev['direction']} ({ev['strategy']}) "
        f"qty {ev.get('qty', '?')} @ {ev.get('entry', '?')}"
    )


def alert_trade_closed(ev: dict[str, Any]) -> None:
    pnl = ev.get("pnl", 0.0)
    icon = "✅" if pnl >= 0 else "❌"
    send_alert(
        f"{icon} <b>CLOSED</b> {ev['symbol']} ({ev['strategy']}) "
        f"{ev.get('reason', '')} · P&L {pnl:+.2f}"
    )
