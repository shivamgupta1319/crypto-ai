# crypto-ai

Personal crypto **futures paper-trading & strategy** system for BTCUSDT/ETHUSDT/SOLUSDT
perpetuals (Binance). Generates signals from multiple strategies, paper-trades with
₹1,00,000 virtual capital + leverage, reports real P&L. Live broker trading is a gated
final phase (Phase 5) — **not built; do not wire a real broker without explicit approval.**
All data sources must stay **free, no API key requiring a card**.

## Stack & layout
- **Backend** (`backend/`): Python 3.12, FastAPI, SQLAlchemy+SQLite, pandas/numpy, httpx.
  - `app/config.py` — all capital/risk/leverage knobs (single source of truth).
  - `app/data/` — Binance public REST candle fetch + SQLite cache (`binance.py`), Fear&Greed (`fng.py`).
  - `app/indicators/` — hand-rolled TA (EMA/RSI/MACD/ATR/ADX/Bollinger/Supertrend/Donchian/VWAP). **No `pandas-ta`** (breaks on NumPy 2.x).
  - `app/strategies/` — `base.py` (registry + contract; `StrategyDef.needs` + `enrich_df`
    attach extra columns like funding) + `library.py` (12 strategies:
    ema_trend_adx, macd_rsi, supertrend, bollinger_meanrev, donchian_breakout, vwap_ema_pullback,
    ichimoku, stochrsi, ttm_squeeze, bollinger_pctb, parabolic_sar, funding_contrarian [perp,
    needs="funding"]).
  - `app/backtest/engine.py` — event-driven backtester with slippage + funding-carry cost,
    annualized Sharpe/Sortino/Calmar/CAGR/expectancy/exposure metrics, and a buy-&-hold benchmark.
  - `app/backtest/robustness.py` — parameter sweep (+heatmap, ±10% perturbation), out-of-sample
    split, walk-forward, Monte Carlo. Exposed at `/api/backtest/{sweep,oos,walkforward,montecarlo}`.
  - `app/backtest/autoselect.py` — screens every coin × strategy × timeframe over a window, ranks
    by a metric with anti-overfit gates (min trades, profitable, OOS-holds-up, no red flags), and can
    auto-promote the recommended top N. Exposed at `/api/backtest/autoselect` (Backtesting → Auto-Select).
  - `app/live/` — `scanner.py` (entry-event detection, reuses strategies), `manager.py`
    (WebSocket broadcast), `scheduler.py` (AsyncIOScheduler, scans every 60s),
    `cycle.py` (shared scan+paper-trade orchestrator used by scheduler + manual scan).
  - `app/broker/` — `base.py` (BrokerInterface), `paper.py` (PaperBroker). Phase 5
    LiveBroker implements the same interface — risk logic in portfolio doesn't change.
  - `app/portfolio/` — `sizing.py` (risk-based sizing), `engine.py` (risk gate + kill
    switch + manage stops/targets + accounting + funding accrual + per-strategy attribution
    + risk view + reset). `pe.broker` is the module-level broker.
  - `app/news/` — free RSS aggregator + keyword sentiment (`get_news`, cached 10min).
  - `app/alerts/` — free Telegram + Discord notifier (`send_alert`); fires on signals/trades
    from the scan cycle. Gated by `.env` creds; no-op + never raises when unconfigured.
  - `app/data/stream.py` — Binance markPrice WS → in-memory price cache; `latest_price`
    prefers it, falls back to REST. Best-effort (resilient if WS unavailable).
  - `app/data/derivatives.py` (N6) — free perp data: funding rate, open interest,
    long/short ratio per symbol + CoinGecko global (BTC dominance/mcap). Cached, best-effort
    (returns None on failure). `funding_history`/`attach_funding` back the funding strategy.
  - `app/regime/` (N10) — rule-based market regime (trending_up/down/ranging/high_vol) from
    ADX+EMA slope+ATR%. `regime_series` (vectorized) + `current_regime`.
  - `app/learning/` (N10 adaptive layer, **advisory/paper-only**) — `features.py` (context
    feature vectors + regime one-hot), `labeling.py` (triple-barrier win/loss labels),
    `dataset.py` (build/persist/load labeled samples — cold-start from backtests),
    `metalabel.py` (scikit-learn GBM P(win) classifier + with/without-filter eval; models in
    gitignored `backend/models/`), `optimizer.py` (walk-forward param proposals), `allocation.py`
    (per-strategy/regime perf → disable/scale proposals), `levers.py` (bounded size multipliers),
    `agent.py` (orchestrator: generate/approve/reject/revert proposals + LLM narrative).
  - `app/settings_store.py` (N9) — runtime-editable risk/leverage/universe overrides on top of
    `config.py`, persisted in the `settings` table, validated + bounded; applied at startup.
  - `app/ai/` — swappable LLM provider wrapper (`__init__.py`: `complete()` routes
    Gemini↔OpenRouter via httpx, returns `None` when unconfigured/on error — never raises;
    `ai_status()`) + `context.py` (pure prompt formatters). **Strictly advisory — never
    sizes or places trades.** Keys in gitignored `.env` (`CRYPTOAI_GEMINI_API_KEY` /
    `CRYPTOAI_OPENROUTER_API_KEY`); both free, no card.
  - `app/api/` — routers: `dashboard.py` (+ `/market/derivatives`, `/market/correlation`),
    `strategies.py`, `backtest.py`, `signals.py`, `portfolio.py`, `news.py`,
    `ai.py` (`/api/ai/{status,commentary,ask,backtest-explain}` — advisory text only),
    `settings.py` (`/api/settings` — runtime knobs), `agent.py` (`/api/agent/*` — N10:
    dataset/regime/model/optimize/overview/review/proposals — advisory, human-approved).
  - `app/models.py` — Candle, ActiveStrategy, Signal, PaperTrade, BacktestRun, Setting,
    TrainingSample, AgentProposal.
- **Frontend** (`frontend/`): React+Vite+TS, Tailwind v4, lightweight-charts.
  - `src/api/client.ts` — typed client. `src/pages/` — Dashboard, Scanner, Portfolio, Backtest,
    News, Agent (adaptive layer), Settings.

## Key invariant — strategies are shared pure functions
A strategy is `generate(df, params) -> df` adding `signal` (target position 1/-1/0) + `atr`.
The **same function** must power both the backtester and the live scanner — never fork the
logic. "Promote to live" just writes a row to `active_strategies` (read by scanner + paper-trader).

## Commands
```bash
# Backend (from backend/)
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
.venv/bin/python -m pytest
.venv/bin/ruff check app migrations tests          # lint (CI runs this)
.venv/bin/alembic revision --autogenerate -m "msg" # new schema migration
.venv/bin/alembic upgrade head                     # apply (also runs at app startup)
# Frontend (from frontend/)
npm run dev        # proxies /api -> :8000; override with VITE_API_PROXY
npm run build      # tsc + vite build (use to typecheck)
```
Note: port 8000/5173 may clash with the user's separate "SmartTrader" project; use the
`VITE_API_PROXY` env + a different uvicorn port if so.

## Conventions
- **Schema changes go through Alembic** (`migrations/`), not `create_all`. App startup runs
  migrations to head (`app/db/migrate.py`); legacy create_all DBs are auto-stamped to baseline.
  Add a column/table → `alembic revision --autogenerate`, review, commit. Tests use an
  in-memory `Base.metadata.create_all` and are independent of migrations.
- Lint with `ruff` (config in `ruff.toml`); keep `ruff check` clean. CI runs ruff + pytest + FE build.
- Backtest metrics/trades must be native Python floats (cast `np.float64`) for JSON.
- No look-ahead: signal on bar i is acted on at open of bar i+1; stops/targets checked intrabar.
- Add a strategy: implement in `library.py`, `register(StrategyDef(...))`, add a test in `tests/`.
- Phased build: follow `docs/features/` flow for non-trivial phases. Phases 2–4 pages are stubbed.

## Optional AI (keys available: Gemini free tier, OpenRouter)
For future AI features (news sentiment, market commentary, strategy suggestions) the user
has free Gemini + OpenRouter keys. Keep keys in `.env` (gitignored); never commit them.
