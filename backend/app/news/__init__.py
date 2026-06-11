"""Crypto news aggregator — free RSS feeds, per-coin filtering, keyword sentiment.

No API key or card required. Feeds are fetched with a short in-process cache so
we don't hammer the sources. Sentiment is a simple, deterministic lexicon score;
the user's Gemini/OpenRouter keys could later replace it for richer analysis.
"""
from __future__ import annotations

import time
from typing import Any

import feedparser

# Public RSS feeds (free, no key).
FEEDS: list[tuple[str, str]] = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/feed"),
]

# Symbol -> keywords used to tag/filter an article.
COIN_KEYWORDS: dict[str, list[str]] = {
    "BTCUSDT": ["bitcoin", "btc"],
    "ETHUSDT": ["ethereum", "ether", "eth"],
    "SOLUSDT": ["solana", "sol"],
}

_POSITIVE = {
    "surge", "rally", "soar", "gain", "gains", "bullish", "jump", "jumps", "adopt",
    "adoption", "approve", "approval", "upgrade", "partnership", "record", "breakout",
    "boost", "rise", "rises", "climb", "climbs", "pump", "high", "wins", "win", "etf",
}
_NEGATIVE = {
    "crash", "plunge", "drop", "drops", "bearish", "hack", "hacked", "exploit", "ban",
    "lawsuit", "sell-off", "selloff", "dump", "fall", "falls", "decline", "fear",
    "liquidation", "liquidated", "scam", "fraud", "slump", "warning", "outage", "down",
}

_CACHE_TTL = 600  # seconds
_cache: dict[str, Any] = {"ts": 0.0, "items": []}


def _sentiment(text: str) -> str:
    words = set(text.lower().replace(",", " ").replace(".", " ").split())
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _tag_coins(text: str) -> list[str]:
    low = text.lower()
    tagged = []
    for symbol, kws in COIN_KEYWORDS.items():
        if any(kw in low for kw in kws):
            tagged.append(symbol)
    return tagged


def _fetch_all() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source, url in FEEDS:
        try:
            parsed = feedparser.parse(url)
        except Exception:
            continue
        for e in parsed.entries[:25]:
            title = getattr(e, "title", "")
            summary = getattr(e, "summary", "")[:280]
            published = getattr(e, "published", "") or getattr(e, "updated", "")
            published_ts = None
            if getattr(e, "published_parsed", None):
                published_ts = int(time.mktime(e.published_parsed) * 1000)
            text = f"{title} {summary}"
            items.append({
                "source": source,
                "title": title,
                "link": getattr(e, "link", ""),
                "summary": summary,
                "published": published,
                "published_ts": published_ts,
                "coins": _tag_coins(text),
                "sentiment": _sentiment(text),
            })
    # Newest first when timestamps are available.
    items.sort(key=lambda i: i["published_ts"] or 0, reverse=True)
    return items


def get_news(coin: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
    now = time.time()
    if now - _cache["ts"] > _CACHE_TTL or not _cache["items"]:
        _cache["items"] = _fetch_all()
        _cache["ts"] = now
    items = _cache["items"]
    if coin:
        items = [i for i in items if coin in i["coins"]]
    return items[:limit]
