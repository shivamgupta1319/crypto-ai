# crypto-ai — Next Development Plan (post-MVP)

**Status as of 2026-06-10:** Phases 0–4 complete + a post-test gap-fix pass (manage/remove
promoted strategies, always-on "Current Setups" snapshot, 1–30x leverage, saved backtest
runs + history, richer live dashboard, Docker + free-port scripts). The paper-trading MVP
runs end-to-end locally: backtest → promote → live scan → auto paper-trade (trailing stops,
kill switch, manual close) → P&L reporting, plus market outlook and news. 39 tests passing.

**Done since (next-development sprints):** N1 (Alembic + ruff + CI + client retries),
N2 (slippage/funding realism + rich metrics + buy&hold), N3 (5 new strategies, 11 total),
N4 (robustness: sweep/heatmap/OOS/walk-forward/Monte Carlo), N5 (Telegram/Discord alerts +
markPrice WS + confidence upgrade), N7 (funding accrual + attribution + risk view +
reset/export), and **N8 (AI layer: Gemini/OpenRouter wrapper + market commentary +
backtest explainer + portfolio Q&A — advisory only)**, **N6 (market intelligence:
funding/OI/long-short + BTC dominance + correlation matrix + funding_contrarian perp
strategy)**, **N9 (runtime Settings page)**, and **N10 (Adaptive Intelligence Layer:
regime detection + triple-barrier feature store + scikit-learn meta-label filter +
walk-forward optimizer + allocation/auto-disable + propose-approve-revert agent + Agent
UI — paper-only, human-in-the-loop)**. **All roadmap items N1–N10 are now built; 110 tests
passing.** Only the deliberately-gated Phase 5 (live broker) remains.

**Scope of this plan:** everything below keeps the system **local + paper only** (no real
broker — that stays gated as Phase 5). The goal of this phase is to **make the strategies
trustworthy** and **harden the system** so that, when you do go live, you're acting on
validated edges with realistic expectations. Still **free, no paid APIs, no card.**

---

## 1. Honest assessment of the current system

**What's solid:** clean shared-strategy architecture (backtest == live), no look-ahead in
the engine, risk controls enforced in one place, real Binance data, working WebSocket
scanner + paper broker, decent test coverage.

**Known limitations to fix (grounded in the code):**
- **Backtest realism:** fees modeled, but **no funding cost** (perps charge funding every
  8h — material over multi-day holds), **no slippage**, `sharpe_per_bar` is not annualized,
  and metrics omit Sortino/Calmar/CAGR/expectancy/exposure/max-consecutive-losses.
- **No robustness testing:** no walk-forward, no parameter sweep, no Monte Carlo, no
  out-of-sample split, no buy-&-hold benchmark. Easy to fool yourself with one good window.
- **Strategies:** only 6, all **single-timeframe**, no higher-timeframe regime filter, and
  `reverse_on_opposite` always reverses (wrong for mean-reversion). No perp-specific edges.
- **Data:** scanner **polls** `latest_price` each cycle — no live WebSocket price stream;
  stop/target checks miss intrabar wicks between 60s cycles.
- **Schema:** `create_all` only — **no migrations**. We've already added columns ad-hoc;
  the next schema change will break any existing local DB. This is the #1 engineering debt.
- **No AI yet** despite available Gemini/OpenRouter keys (news sentiment is keyword-only).
- **No alerts** — you must watch the screen to catch signals during the test month.

---

## 2. Guiding principles (this phase)

1. **Trust before scale** — invest first in backtest rigor + more strategies, so promotion
   to live signals means something.
2. **Avoid overfitting** (industry data: ~90% of crypto strategies are overfit). Enforce:
   ≥3 years of data spanning bull/bear/range, ≥100 trades for significance, edge must
   survive **±10% parameter perturbation**, and treat win-rate >80% / profit-factor >4 /
   near-zero drawdown as **red flags**, not victories. (See sources at the end.)
3. **Realistic friction** — model funding + slippage in *both* backtest and paper so they
   agree, and so they'll agree with live later.
4. **Free + local only** — no paid data, no real broker this phase.
5. **Small vertical slices** — each item below is shippable via your
   `/create-feature → /execute-phase → /verify-feature` flow, ≤~500 LOC.

---

## 3. Workstreams

### A. Backtesting rigor & realism  ⭐ HIGH
- **Funding + slippage** in the engine (and mirror in PaperBroker) for parity.
- **Richer metrics:** CAGR (over real duration), annualized Sharpe + Sortino, Calmar,
  expectancy (avg R × win%), max consecutive losses, avg hold time, exposure %, MAE/MFE.
- **Buy-&-hold benchmark** overlaid on every backtest.
- **Train/test split** (out-of-sample): optimize on first 70%, report on last 30%.
- **Parameter sweep / grid search:** sweep a strategy's params, return a ranked table +
  a 2-param **heatmap**; flag params whose edge collapses under ±10% perturbation.
- **Walk-forward analysis:** rolling optimize→test windows; report per-window consistency.
- **Monte Carlo:** shuffle trade order + jitter fills over N iterations → drawdown/return
  confidence bands (so you size risk to the 95th-percentile drawdown, not the lucky path).
- **Saved backtest runs:** persist runs to DB, list/compare historically.
- **Price chart with trade markers:** candlesticks + entry/exit/stop markers (lightweight-charts).

### B. Strategy library expansion  ⭐ HIGH  (full catalog in §4)
- Add ~10 strategies across trend / momentum / mean-reversion / volatility-breakout /
  **perp-specific** (funding & OI) / **multi-factor composite**.
- Add a reusable **higher-timeframe regime filter** wrapper (e.g., only long when the 4h
  trend is up) usable by any strategy — this alone typically lifts quality more than new
  indicators.
- Make `reverse_on_opposite` and "exit-on-signal-flip" **per-strategy** flags.

### C. Signal/Scanner intelligence & alerts  MED–HIGH
- **Multi-timeframe / multi-indicator confidence** score (replace ADX-only proxy).
- **Free alerts:** Telegram bot (BotFather, `sendMessage`) and/or Discord webhook on new
  signals & trade events — both 100% free, no card. Essential for a hands-off test month.
- **Browser notifications** (Web Notifications API) when the tab is open.
- **"Scan-all" preview mode:** evaluate every strategy (not just promoted) for a watchlist.
- Signal **staleness/expiry** (a signal older than N bars is stale).

### D. Paper-trading depth & risk analytics  MED
- **Funding accrual** on open positions over time (ties to A).
- **Scale-out / partial TP** (TP1/TP2) + **move-to-breakeven** after TP1.
- **Strategy-level P&L attribution** (which strategy actually makes money).
- **Risk dashboard:** current gross/net exposure, margin usage, per-symbol concentration,
  rough liquidation price per position, correlation warning (BTC/ETH/SOL move together).
- **Reset paper account** button; **CSV/JSON export** of trades; periodic (daily) stats.

### E. Market intelligence & data  MED
- **Funding rate, Open Interest, Long/Short ratio** per coin (free Binance endpoints) on
  the dashboard + as optional strategy inputs.
- **BTC dominance & total market cap** (CoinGecko `/global`, free, no key).
- **Live price WebSocket** stream from Binance (`<symbol>@markPrice` / kline streams) to
  replace polling — lower latency, fewer REST calls, enables tighter stop checks.
- **Correlation matrix** + per-coin candle chart with indicators on the dashboard.

### F. AI layer (Gemini free tier + OpenRouter)  MED
- Thin provider wrapper (`app/ai/`) swappable Gemini↔OpenRouter, key in gitignored `.env`.
- **LLM news sentiment** (replace keyword lexicon) + per-coin news digest.
- **Daily market commentary** synthesizing regime + funding/OI + news + your open risk.
- **Natural-language portfolio Q&A** ("how did supertrend do this week?").
- **Backtest interpreter:** plain-English summary of a run + overfitting caution flags.
- Strictly advisory — **AI never sizes or places trades.**

### G. Engineering, quality & infra  ⭐ HIGH (migrations first)
- **Alembic migrations** — stop using `create_all` for schema changes (#1 debt).
- **Ruff + mypy** for the backend; wire **CI** (GitHub Actions) running pytest + lint + the
  frontend build.
- **Binance client hardening:** retries/backoff, rate-limit awareness, gap detection in
  the candle cache.
- **Structured logging** + a small **/health/status** panel (last scan time, scheduler
  state, feed freshness, errors) surfaced in the UI.
- **Dockerfile + docker-compose** for one-command local run.
- Expand tests: engine funding/slippage, walk-forward, alerts, AI wrapper (mocked).

### H. UX / quality-of-life  LOW–MED
- **Settings page** to edit risk/leverage/universe/timeframes (persisted) instead of editing
  `config.py`.
- Configurable **symbol universe** (add coins beyond BTC/ETH/SOL).
- Dark/light toggle, loading/empty/error states polish, mobile layout.

---

## 4. New strategies catalog (the explicit ask)

Each is a pure `generate(df, params)` returning `signal`(1/-1/0) + `atr`, fitting the
existing registry. Suggested additions:

**Trend**
- **Ichimoku Cloud** — price vs cloud + Tenkan/Kijun cross; strong on BTC/ETH 4h.
- **EMA Ribbon (8/13/21/34/55)** — fan alignment for trend strength/continuation.
- **Heikin-Ashi trend** — smoothed HA candles to filter chop.
- **ADX/DI crossover** — +DI/−DI cross gated by rising ADX.

**Momentum**
- **ROC / Momentum** — rate-of-change threshold with sign filter.
- **StochRSI** — overbought/oversold crosses in trend direction.
- **MACD histogram reversal** — histogram slope turns + zero-line context.

**Mean-reversion**
- **Bollinger %B + z-score** — fade statistical extremes; ranging-regime only.
- **RSI(2) pullback (Connors)** — classic short-term mean reversion in an uptrend.
- **Keltner ↔ price re-entry** — revert to the Keltner mid.

**Volatility / breakout**
- **TTM Squeeze** (Bollinger inside Keltner → release) — explosive breakout timing; great
  for SOL.
- **Parabolic SAR** flip — trailing trend with built-in stop.
- **ATR channel breakout** — close beyond N×ATR band with volume.

**Perp-specific (uses free Binance derivatives data)**
- **Funding-rate contrarian** — extreme positive funding (crowded longs) → fade; extreme
  negative → favor longs. Pure perp edge, no equity-market analog.
- **OI + price divergence** — rising price on falling OI = weak move (caution/fade);
  rising price + rising OI = conviction (follow).
- **Long/short ratio extreme** — crowd positioning as a contrarian filter.

**Multi-factor / composite**
- **HTF-regime + LTF-entry** (the wrapper from §B) applied to any base strategy.
- **Confluence score** — combine trend + momentum + volatility votes; trade only on
  agreement (higher win-rate, fewer trades).
- **News/sentiment-gated** — block or de-size entries when AI sentiment strongly opposes
  (ties to §F).
- *(Optional, advanced)* **ML classifier** — logistic-regression/gradient-boost on indicator
  features predicting next-bar direction; treated as just another signal source, fully
  backtested like the rest. Strictly opt-in given overfitting risk.

> Discipline: every new strategy must pass §3.A robustness checks (out-of-sample +
> ±10% perturbation + ≥100 trades) before it's eligible to promote to live signals.

---

## 5. Recommended phased roadmap (ordered)

Each "Next-Phase" is an independent, testable slice. Recommended order:

1. **N1 — Engineering foundation:** Alembic migrations, ruff/mypy, CI, client retries.
   *(Unblocks safe schema changes for everything after; do this first.)*
2. **N2 — Backtest realism + metrics + buy&hold + trade-marked chart.** Makes results
   honest and readable.
3. **N3 — Strategy expansion wave 1** (HTF regime filter wrapper + 5 strategies:
   Ichimoku, StochRSI, TTM Squeeze, Bollinger %B, Parabolic SAR) with the new metrics.
4. **N4 — Robustness suite:** parameter sweep + heatmap, out-of-sample split,
   walk-forward, Monte Carlo. Now you can *trust* a promotion.
5. **N5 — Alerts + live price WebSocket + scanner confidence upgrade.** Hands-off test month.
6. **N6 — Market intelligence:** ✅ done — funding/OI/long-short + BTC dominance/mcap
   (CoinGecko) + correlation matrix on the Dashboard + `funding_contrarian` perp strategy
   (backtestable via `StrategyDef.needs`/`enrich_df` funding attachment).
7. **N7 — Paper-trading depth:** funding accrual, scale-out/breakeven, strategy P&L
   attribution, risk dashboard, reset/export.
8. **N8 — AI layer:** ✅ done — swappable Gemini/OpenRouter wrapper (`app/ai/`), daily
   market commentary, backtest explainer with overfitting flags, portfolio Q&A. Advisory only.
9. **N9 — UX:** ✅ done — runtime Settings page (editable risk/leverage/universe/timeframes,
   persisted to the `settings` table, validated + bounded; applied at startup via `settings_store`).
10. **N10 — Adaptive Intelligence Layer (self-improving agent):** ✅ done — `app/regime/`
    (rule-based regime), `app/learning/` (triple-barrier feature store, scikit-learn meta-label
    P(win) filter with with/without backtest comparison, walk-forward optimizer, allocation/
    auto-disable analysis, bounded levers, and the propose→approve→revert orchestrator) + the
    **Agent** UI page. Paper-only, human-in-the-loop. Full design:
    **[ADAPTIVE_INTELLIGENCE_LAYER.md](ADAPTIVE_INTELLIGENCE_LAYER.md)**.
11. **(Later, gated) Phase 5 — Live broker:** `LiveBroker` implementing the existing
    `BrokerInterface` in **dry-run** first, then real with explicit confirmation + kill switch.

---

## 6. Free data sources (verified, no key / no card)

| Need | Source / endpoint |
| --- | --- |
| Candles, price | Binance `GET /fapi/v1/klines`, `/fapi/v1/ticker/price` (already used) |
| Live price stream | Binance WS `<symbol>@markPrice`, `<symbol>@kline_<tf>` |
| Funding rate | Binance `GET /fapi/v1/fundingRate` (history), `/fapi/v1/fundingInfo` |
| Open interest | `GET /fapi/v1/openInterest`, `GET /futures/data/openInterestHist` |
| Long/short ratio | `GET /futures/data/globalLongShortAccountRatio` |
| Fear & Greed | alternative.me `/fng` (already used) |
| BTC dominance / mkt cap | CoinGecko `GET /api/v3/global` (free, no key) |
| News | RSS via feedparser (already used) |
| Alerts | Telegram Bot API (`sendMessage`) / Discord webhooks (free) |
| AI | Gemini free tier / OpenRouter (your keys; `.env`, gitignored) |
| ML / regime (N10) | `scikit-learn` (meta-label classifier), optional `hmmlearn` (regimes), `joblib` (model persistence) — all free, local |

---

## 7. Anti-overfitting guardrails (bake into the tooling)

- Require **out-of-sample** confirmation before any "promote to live".
- Show **±10% parameter-perturbation** stability on the backtest result card.
- Surface **Monte Carlo 95th-percentile drawdown**, not just the realized path.
- Auto-flag suspicious results (win% > 80, PF > 4, DD ≈ 0, trades < 100) with a warning.
- Always compare against **buy-&-hold** for the same window.

---

## 8. Open decisions to confirm before building

1. **Start point** — recommend N1 (engineering foundation) so later schema/data changes are
   safe; or jump straight to N2/N3 if you'd rather see strategy/backtest value first.
2. **Alerts channel** — Telegram vs Discord (or both)? Telegram is the simplest free setup.
3. **AI provider default** — Gemini or OpenRouter as primary? (Wrapper supports both.)
4. **Symbol universe** — keep BTC/ETH/SOL for now, or widen during testing?

---

## 9. Phase 6 — Adaptive Intelligence Layer (self-improving agent)

This is large enough to live in its own design doc: **[ADAPTIVE_INTELLIGENCE_LAYER.md](ADAPTIVE_INTELLIGENCE_LAYER.md)**.

In short: a bounded, human-in-the-loop agent that learns from market conditions, past trades,
and backtests to **cut loss-making trades** — via meta-labeling (filter bad signals), regime
detection, walk-forward re-optimization, and performance-based allocation. Propose-and-approve,
paper-only, fully guarded against overfitting. Depends on N2/N4/N7/N8; it's the last build
phase before the gated live broker. See the linked doc for the staged plan and guardrails.

---

### Sources
- Binance USDⓈ-M futures public market-data endpoints (funding/OI/long-short, no key):
  https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History ,
  https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics ,
  https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio
- Backtesting robustness / overfitting (walk-forward, Monte Carlo, ±10% perturbation,
  3-yr multi-regime data, ≥100 trades, red flags):
  https://trendrider.net/blog/how-to-avoid-overfitting-crypto-trading ,
  https://www.interactivebrokers.com/campus/ibkr-quant-news/the-future-of-backtesting-a-deep-dive-into-walk-forward-analysis/ ,
  https://www.blockchain-council.org/cryptocurrency/backtesting-ai-crypto-trading-strategies-avoiding-overfitting-lookahead-bias-data-leakage/
