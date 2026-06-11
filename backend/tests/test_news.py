"""News sentiment + coin-tagging tests (pure functions, no network)."""
from __future__ import annotations

from app.news import _sentiment, _tag_coins


def test_sentiment_positive():
    assert _sentiment("Bitcoin surges to record high on ETF approval") == "positive"


def test_sentiment_negative():
    assert _sentiment("Major exchange hacked in exploit, market crash fears") == "negative"


def test_sentiment_neutral():
    assert _sentiment("Ethereum developers schedule a routine meeting") == "neutral"


def test_tag_coins_detects_symbols():
    assert "BTCUSDT" in _tag_coins("Bitcoin rallies hard")
    assert "ETHUSDT" in _tag_coins("Ethereum upgrade goes live")
    assert "SOLUSDT" in _tag_coins("Solana network sees growth")


def test_tag_coins_none_when_unrelated():
    assert _tag_coins("Stock market closes higher today") == []
