"""Pure formatters that turn system data into compact prompt context.

Kept separate from the provider wrapper and the API so they're trivially
testable (string-in / string-out, no network or DB).
"""
from __future__ import annotations

from typing import Any


def format_outlook(outlook: dict[str, Any]) -> str:
    fng = outlook.get("fear_greed") or {}
    fng_line = ""
    if isinstance(fng, dict) and fng.get("value") is not None:
        fng_line = f"Fear & Greed: {fng.get('value')} ({fng.get('classification', '')}). "
    lines = [
        f"Market breadth: {outlook.get('market_breadth', 'unknown')}. {fng_line}".strip()
    ]
    for c in outlook.get("coins", []):
        if not c.get("available"):
            lines.append(f"- {c.get('symbol')}: data unavailable")
            continue
        lines.append(
            f"- {c['symbol']}: price {c['price']}, 24h {c['change_24h_pct']:+}%, "
            f"regime {c['regime']}, RSI {c['rsi']}, ADX {c['adx']}, "
            f"MACD {c['macd_state']}, ATR {c['atr_pct']}%, vol x{c['vol_ratio']}"
        )
    return "\n".join(lines)


def format_account(summary: dict[str, Any], attribution: list[dict[str, Any]]) -> str:
    lines = [
        f"Equity: {summary.get('equity')} {summary.get('display_currency', '')}, "
        f"balance {summary.get('balance')}, "
        f"realized P&L {summary.get('realized_pnl')} ({summary.get('return_pct')}%), "
        f"unrealized {summary.get('unrealized_pnl')}.",
        f"Open positions: {summary.get('open_positions')}, "
        f"closed trades: {summary.get('closed_trades')}, "
        f"win rate {summary.get('win_rate')}%, "
        f"kill switch {'ON' if summary.get('kill_switch') else 'off'}.",
    ]
    if attribution:
        lines.append("Per-strategy (net P&L, trades, win%):")
        for a in attribution[:10]:
            lines.append(
                f"- {a['strategy']}: {a['net_pnl']} over {a['trades']} trades, "
                f"win {a['win_rate']}%, PF {a.get('profit_factor')}"
            )
    return "\n".join(lines)


def format_positions(positions: list[dict[str, Any]]) -> str:
    if not positions:
        return "No open positions."
    lines = ["Open positions:"]
    for p in positions:
        lines.append(
            f"- {p['symbol']} {p['direction']} qty {p['qty']} @ {p['entry_price']} "
            f"(now {p['current_price']}), stop {p.get('stop')}, target {p.get('target')}, "
            f"lev {p.get('leverage')}x, uPnL {p['unrealized_pnl']} [{p['strategy']}]"
        )
    return "\n".join(lines)


def format_news(items: list[dict[str, Any]], limit: int = 12) -> str:
    if not items:
        return "No recent headlines."
    lines = ["Recent headlines (source, sentiment):"]
    for n in items[:limit]:
        coins = ",".join(n.get("coins", [])) or "general"
        lines.append(f"- [{n.get('sentiment')}/{coins}] {n.get('title')} ({n.get('source')})")
    return "\n".join(lines)


def format_backtest_run(run: dict[str, Any]) -> str:
    """``run`` is a BacktestRun-shaped dict: symbol/timeframe/start/end/leverage +
    a ``summary`` list of per-strategy metric dicts."""
    lines = [
        f"Backtest: {run.get('symbol')} {run.get('timeframe')} from "
        f"{run.get('start')} to {run.get('end')}, leverage {run.get('leverage')}x, "
        f"risk/trade {run.get('risk_per_trade_pct')}%, {run.get('candles')} candles.",
    ]
    for s in run.get("summary", []):
        lines.append(
            f"- {s.get('strategy')}: return {s.get('return_pct')}%, "
            f"net P&L {s.get('net_pnl')}, trades {s.get('total_trades')}, "
            f"win {s.get('win_rate')}%, max DD {s.get('max_drawdown_pct')}%, "
            f"profit factor {s.get('profit_factor')}"
        )
    return "\n".join(lines)
