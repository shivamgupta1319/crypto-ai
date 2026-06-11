"""Tests for alerts (mocked HTTP), price-stream cache, and confidence scoring."""
from __future__ import annotations

import app.alerts as alerts
from app.data import stream
from app.live.scanner import _confidence


# --- alerts (no network: monkeypatch settings + httpx) ------------------------
def test_send_alert_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(alerts.settings, "telegram_bot_token", "")
    monkeypatch.setattr(alerts.settings, "telegram_chat_id", "")
    monkeypatch.setattr(alerts.settings, "discord_webhook_url", "")
    assert alerts.send_alert("hi") is False


def test_send_alert_posts_to_discord(monkeypatch):
    monkeypatch.setattr(alerts.settings, "discord_webhook_url", "https://discord/webhook")
    calls = {}

    class _Resp:
        status_code = 204

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["json"] = kwargs.get("json")
        return _Resp()

    monkeypatch.setattr(alerts.httpx, "post", fake_post)
    assert alerts.send_alert("hello") is True
    assert calls["url"] == "https://discord/webhook"
    assert calls["json"]["content"] == "hello"


def test_alert_signal_formats_without_raising(monkeypatch):
    sent = {}
    monkeypatch.setattr(alerts, "send_alert", lambda text: sent.setdefault("text", text) or True)
    alerts.alert_signal({"direction": "LONG", "symbol": "BTCUSDT", "timeframe": "15m",
                         "strategy": "supertrend", "entry": 100, "stop": 98, "target": 104,
                         "rr": 2.0, "confidence": 0.6})
    assert "SIGNAL" in sent["text"] and "BTCUSDT" in sent["text"]


# --- price stream cache -------------------------------------------------------
def test_price_cache_set_get():
    stream.set_price("BTCUSDT", 61000.0)
    assert stream.get_cached_price("BTCUSDT") == 61000.0
    assert stream.get_cached_price("NOPE") is None


def test_price_cache_staleness(monkeypatch):
    stream.set_price("ETHUSDT", 3000.0)
    # Force the entry to look old.
    price, ts = stream._prices["ETHUSDT"]
    stream._prices["ETHUSDT"] = (price, ts - stream._STALE_SECONDS - 5)
    assert stream.get_cached_price("ETHUSDT") is None


def test_latest_price_prefers_cache(monkeypatch):
    from app.data import binance
    stream.set_price("SOLUSDT", 150.0)
    # If REST were hit it would raise here; cache must short-circuit it.
    monkeypatch.setattr(binance.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("REST hit")))
    assert binance.latest_price("SOLUSDT") == 150.0


# --- confidence ---------------------------------------------------------------
def test_confidence_in_range_and_direction_aware(trending_up):
    from app.strategies.base import run_strategy
    ann = run_strategy("supertrend", trending_up)
    c_long = _confidence(ann, 1)
    c_flat = _confidence(ann, 0)
    assert 0.2 <= c_long <= 0.97
    assert 0.2 <= c_flat <= 0.97
    # In a clean uptrend, a long should be at least as confident as a direction-less read.
    assert c_long >= c_flat
