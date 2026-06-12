"""AI layer tests — no network. Cover the no-key fallback, provider routing
(mocked httpx), and the pure context formatters."""
from __future__ import annotations

import pytest

import app.ai as ai
from app.ai import context as ctx


# --- provider selection / status ---------------------------------------------
def test_disabled_when_no_keys(monkeypatch):
    monkeypatch.setattr(ai.settings, "ai_provider", "auto")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "")
    monkeypatch.setattr(ai.settings, "openrouter_api_key", "")
    assert ai.settings.active_ai_provider is None
    assert ai.settings.ai_enabled is False
    assert ai.ai_status()["enabled"] is False
    # complete() must return None (not raise) when unconfigured.
    assert ai.complete("hello") is None


def test_auto_prefers_gemini(monkeypatch):
    monkeypatch.setattr(ai.settings, "ai_provider", "auto")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "g")
    monkeypatch.setattr(ai.settings, "openrouter_api_key", "o")
    assert ai.settings.active_ai_provider == "gemini"


def test_auto_falls_back_to_openrouter(monkeypatch):
    monkeypatch.setattr(ai.settings, "ai_provider", "auto")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "")
    monkeypatch.setattr(ai.settings, "openrouter_api_key", "o")
    assert ai.settings.active_ai_provider == "openrouter"


def test_explicit_none_disables(monkeypatch):
    monkeypatch.setattr(ai.settings, "ai_provider", "none")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "g")
    assert ai.settings.active_ai_provider is None


# --- provider routing (mocked httpx) -----------------------------------------
class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_gemini_routing(monkeypatch):
    monkeypatch.setattr(ai.settings, "ai_provider", "gemini")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "g")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _Resp({"candidates": [{"content": {"parts": [{"text": "  hi there  "}]}}]})

    monkeypatch.setattr(ai.httpx, "post", fake_post)
    out = ai.complete("question", system="sys")
    assert out == "hi there"
    assert "generativelanguage.googleapis.com" in captured["url"]
    assert captured["json"]["system_instruction"]["parts"][0]["text"] == "sys"


def test_openrouter_routing(monkeypatch):
    monkeypatch.setattr(ai.settings, "ai_provider", "openrouter")
    monkeypatch.setattr(ai.settings, "openrouter_api_key", "o")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return _Resp({"choices": [{"message": {"content": "answer"}}]})

    monkeypatch.setattr(ai.httpx, "post", fake_post)
    out = ai.complete("question")
    assert out == "answer"
    assert "openrouter.ai" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer o"


def test_complete_raises_on_error(monkeypatch):
    monkeypatch.setattr(ai.settings, "ai_provider", "gemini")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "g")
    monkeypatch.setattr(ai.settings, "openrouter_api_key", "")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(ai.httpx, "post", boom)
    with pytest.raises(ai.AIError):  # configured-but-failing now raises
        ai.complete("x")


def test_complete_falls_back_to_openrouter_on_429(monkeypatch):
    # auto mode + both keys: a Gemini 429 should fall back to OpenRouter.
    monkeypatch.setattr(ai.settings, "ai_provider", "auto")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "g")
    monkeypatch.setattr(ai.settings, "openrouter_api_key", "o")

    class _Req:
        pass

    class _Resp429:
        status_code = 429

    def fake_post(url, **kwargs):
        if "generativelanguage" in url:
            raise ai.httpx.HTTPStatusError("429", request=_Req(), response=_Resp429())
        return _Resp({"choices": [{"message": {"content": "fallback answer"}}]})

    monkeypatch.setattr(ai.httpx, "post", fake_post)
    assert ai.complete("q") == "fallback answer"


def test_all_providers_rate_limited_raises(monkeypatch):
    monkeypatch.setattr(ai.settings, "ai_provider", "gemini")
    monkeypatch.setattr(ai.settings, "gemini_api_key", "g")
    monkeypatch.setattr(ai.settings, "openrouter_api_key", "")

    class _Req:
        pass

    class _Resp429:
        status_code = 429

    def fake_post(url, **kwargs):
        raise ai.httpx.HTTPStatusError("429", request=_Req(), response=_Resp429())

    monkeypatch.setattr(ai.httpx, "post", fake_post)
    with pytest.raises(ai.AIRateLimited):
        ai.complete("x")


# --- context formatters (pure) -----------------------------------------------
def test_format_outlook():
    out = ctx.format_outlook({
        "market_breadth": "bullish",
        "fear_greed": {"value": 55, "classification": "Greed"},
        "coins": [
            {"symbol": "BTCUSDT", "available": True, "price": 60000, "change_24h_pct": 1.5,
             "regime": "uptrend", "rsi": 60, "adx": 25, "macd_state": "bullish",
             "atr_pct": 2.0, "vol_ratio": 1.1},
            {"symbol": "ETHUSDT", "available": False},
        ],
    })
    assert "bullish" in out and "Greed" in out
    assert "BTCUSDT" in out and "uptrend" in out
    assert "ETHUSDT: data unavailable" in out


def test_format_account_and_positions():
    acct = ctx.format_account(
        {"equity": 101000, "balance": 101000, "realized_pnl": 1000, "return_pct": 1.0,
         "unrealized_pnl": 0, "open_positions": 1, "closed_trades": 5, "win_rate": 60,
         "kill_switch": False, "display_currency": "USDT"},
        [{"strategy": "supertrend", "net_pnl": 800, "trades": 3, "win_rate": 66.6,
          "profit_factor": 2.1}],
    )
    assert "supertrend" in acct and "win rate 60%" in acct
    assert ctx.format_positions([]) == "No open positions."


def test_format_backtest_run():
    out = ctx.format_backtest_run({
        "symbol": "BTCUSDT", "timeframe": "1h", "start": "2024-01-01", "end": "2024-06-01",
        "leverage": 3, "risk_per_trade_pct": 1.0, "candles": 1000,
        "summary": [{"strategy": "macd_rsi", "return_pct": 12.0, "net_pnl": 12000,
                     "total_trades": 40, "win_rate": 55, "max_drawdown_pct": 8,
                     "profit_factor": 1.8}],
    })
    assert "macd_rsi" in out and "BTCUSDT" in out and "profit factor 1.8" in out
