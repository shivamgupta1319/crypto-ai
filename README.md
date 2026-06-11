# crypto-ai — Crypto Futures Paper-Trading & Strategy System

A personal system to analyze the crypto futures market (BTCUSDT, ETHUSDT, SOLUSDT
perpetuals on Binance), generate trade signals from multiple strategies, **paper-trade**
them with ₹1,00,000 of virtual capital and leverage, and report real P&L — so strategies
can be validated over ~1 month before any real money is risked.

> ⚠️ **Paper trading only.** Live broker trading is a deliberately gated final phase
> (not built yet). Automated leveraged futures are high-risk; this tool exists to test
> first. Everything uses **free** data sources — no paid APIs, no card required.

## Status — Phases 0–4 complete (paper-trading MVP done)
- ✅ Backend foundations (FastAPI + SQLite), Binance candle pipeline, Fear&Greed
- ✅ 6-strategy library (shared pure functions used by backtest **and** the live scanner)
- ✅ Backtest engine + API + UI (metrics, equity curve, trade log, "promote to live")
- ✅ Dashboard (live market outlook)
- ✅ **Live Scanner** — scheduler scans promoted strategies every 60s, emits signals
  (entry/stop/target/R:R/confidence), pushes live over WebSocket; Scanner page
- ✅ **Paper Trading / Portfolio** — `PaperBroker` (behind a broker interface) auto-opens
  positions from signals with risk limits (sizing, leverage cap, max concurrent, daily-loss
  kill switch), **trailing stops**, **manual close**, live unrealized/realized P&L, win rate,
  equity curve, trade history; Portfolio page polls every 5s + refreshes live on trade events
- ✅ **News** — aggregated free RSS (CoinDesk, Cointelegraph, Decrypt, …), per-coin filter,
  keyword sentiment tag (no key/card). **Dashboard** now also shows paper-account snapshot
  + latest signals
- ✅ **Post-MVP sprints (N1–N10):**
  - **N1–N5, N7** — Alembic migrations + ruff + CI; backtest realism (slippage + funding) and
    rich metrics + buy&hold; 5 extra strategies; robustness suite (sweep/heatmap/OOS/walk-forward/
    Monte Carlo); Telegram/Discord alerts + markPrice WS; funding accrual + P&L attribution +
    risk view + reset/export.
  - **N6 — Market intelligence:** funding rate / open interest / long-short ratio per coin +
    BTC dominance & total mcap (CoinGecko) + a correlation matrix on the Dashboard, plus a
    perp-specific `funding_contrarian` strategy (12 strategies total).
  - **N8 — AI layer (advisory):** Gemini/OpenRouter wrapper — market commentary, backtest
    explainer, portfolio Q&A. Never sizes or places trades.
  - **N9 — Settings page:** edit risk/leverage/universe/timeframes at runtime (persisted), bounded.
  - **N10 — Adaptive Intelligence Layer (the self-improving agent):** regime detection,
    triple-barrier feature/outcome logging, a scikit-learn **meta-label P(win) filter**
    (with/without backtest comparison), a walk-forward **auto-optimizer**, **allocation/
    auto-disable** analysis, and an **Agent page** where the agent proposes bounded changes you
    **approve/reject/revert**. Paper-only; the agent never trades on its own.
- 🔒 Phase 5 Live broker — gated, after the testing period

## Stack
- **Backend:** Python 3.12, FastAPI, SQLAlchemy + SQLite, pandas/numpy (hand-rolled
  indicators — no `pandas-ta`), httpx, scikit-learn (meta-label model). Binance public REST
  for market data (no key).
- **Frontend:** React + Vite + TypeScript, TailwindCSS v4, lightweight-charts.

## Run it

### Option A — Docker (recommended, one command)
```bash
./scripts/start.sh
```
This **verifies the host ports are free** (auto-picking the next free one), builds both
images, and starts the stack. Defaults to `frontend → http://localhost:5190` and
`backend → http://localhost:8090` (chosen to avoid the common 8000/5173 clash). nginx serves
the built UI and proxies `/api` + the live WebSocket to the backend. The SQLite DB + candle
cache persist in the `cryptoai-data` Docker volume across restarts.

Override the starting ports if you like: `BACKEND_PORT=9000 FRONTEND_PORT=6000 ./scripts/start.sh`.

### Option B — Local dev (auto free ports)
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
cd frontend && npm install && cd ..
./scripts/dev-local.sh      # finds free ports, wires the Vite proxy, runs both
```

### Option C — Manual
```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000   # terminal 1
cd frontend && npm run dev                                                    # terminal 2
```
Vite proxies `/api` → `http://127.0.0.1:8000`. If 8000 is taken:
`VITE_API_PROXY=http://127.0.0.1:8009 npm run dev` + uvicorn on `--port 8009`.

### Tests
```bash
cd backend && .venv/bin/python -m pytest
```

### Optional: free alerts (Telegram / Discord)
Get pinged on new signals and trade opens/closes. All free, no card. Put creds in
`backend/.env` (gitignored):
```bash
# Telegram: create a bot via @BotFather, get your chat id from @userinfobot
CRYPTOAI_TELEGRAM_BOT_TOKEN=123456:ABC...
CRYPTOAI_TELEGRAM_CHAT_ID=123456789
# and/or a Discord channel webhook URL
CRYPTOAI_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```
Leave them unset to disable (the Scanner shows an "alerts on/off" badge). A live Binance
mark-price WebSocket feeds fresh prices when available, falling back to REST automatically.

### Optional: AI insights (Gemini / OpenRouter)
Plain-English market commentary (Dashboard), a backtest explainer with overfitting flags
(Backtesting), and natural-language Q&A about your paper account (Portfolio). **Strictly
advisory — the AI never sizes or places a trade.** Both providers have free tiers (no card).
Put a key in `backend/.env`:
```bash
# Gemini (free tier): https://aistudio.google.com/apikey
CRYPTOAI_GEMINI_API_KEY=AIza...
# and/or OpenRouter (free models): https://openrouter.ai/keys
CRYPTOAI_OPENROUTER_API_KEY=sk-or-...
# Optional overrides:
# CRYPTOAI_AI_PROVIDER=auto            # auto | gemini | openrouter | none
# CRYPTOAI_GEMINI_MODEL=gemini-2.0-flash
# CRYPTOAI_OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
```
With no key set, the AI cards show an "AI off" badge and a hint — everything else works.

## Strategy library (12)
`ema_trend_adx`, `macd_rsi`, `supertrend`, `bollinger_meanrev`, `donchian_breakout`,
`vwap_ema_pullback`, `ichimoku`, `stochrsi`, `ttm_squeeze`, `bollinger_pctb`, `parabolic_sar`,
`funding_contrarian` (perp-specific — fades extreme funding using attached funding data).
Each emits a per-bar target position + ATR; stops are ATR-based and targets are R-multiples.
The **same function** drives backtests and live signals, so a backtested edge behaves
identically live. **All strategies trade both long and short.** Backtests model **slippage +
funding carry** and report annualized **Sharpe/Sortino/Calmar, CAGR, expectancy, max
consecutive losses, exposure**, and a **buy-&-hold benchmark**.

## Live signals — how to see them
The scanner only emits a *triggered* signal on the bar a strategy **flips direction**, so
the **Scanner → Current Setups** table shows each promoted strategy's live state
(LONG/SHORT/FLAT + entry/stop/target) at all times — promote a strategy on a fast timeframe
(`5m`/`15m`) and it appears immediately. "Scan now" forces a refresh. Backtest results are
saved and viewable under **Backtesting → History**.

## Risk controls (in `backend/app/config.py`)
Risk per trade %, max leverage cap, max concurrent positions, max position size, daily
max-loss kill switch, taker fees. These apply to paper trading and (later) live trading.
