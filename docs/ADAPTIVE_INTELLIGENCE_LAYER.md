# crypto-ai — Adaptive Intelligence Layer (Self-Improving Agent)

> A standalone design doc for the "learning agent" idea. It is **Phase 6 / N10** in the
> roadmap (`NEXT_DEVELOPMENT_PLAN.md`), kept separate because it's large and depends on
> several earlier workstreams. Status: **built** (all six stages) — `app/regime/`,
> `app/learning/{features,labeling,dataset,metalabel,optimizer,allocation,levers,agent}.py`,
> the `/api/agent/*` routes, and the **Agent** UI page. Paper-only, propose-and-approve.

**In one line:** turn the system from *fixed rules* into *rules that quietly improve
themselves* by learning from results and market conditions — to take **fewer bad trades**.
It's a "coach" for the system, **not** a money-printer, and it stays **paper-only with the
user approving every change** until proven.

## Why this is realistic (and where the fantasy version fails)
Research is blunt: ML/RL trading bots routinely look great in backtest and disappoint live
because of **overfitting, look-ahead leakage, and non-stationary/regime-changing markets**.
So we build the *disciplined* form — four proven techniques, bounded levers, human approval —
not an unconstrained "AI that prints money."

## The four proven techniques (why, not magic)
- **Meta-labeling** (López de Prado) — *the core loss-reducer.* A secondary ML model scores
  each base-strategy signal with `P(win)` from features (indicators + regime + confidence)
  and **suppresses the low-quality trades**. Built to cut false positives and raise Sharpe.
- **Regime detection** — classify the market (trending / ranging / high-volatility) and only
  run each strategy where it actually works ("learn from market conditions").
- **Walk-forward re-optimization** — periodically re-tune params on rolling windows; adopt
  only if they beat the current config **out-of-sample** ("improve itself" without overfitting).
- **Performance-based allocation / auto-disable** — track per-(strategy, regime) results;
  shrink/disable persistent losers, favor winners ("learn from past trades").

## Staged build (each stage delivers value; ordered)
1. **Data foundation** — log signal/entry **context features** + outcome via **triple-barrier
   labels** (target-first / stop-first / timeout). Add a `signal_features` / `trade_outcomes`
   store; extends the per-strategy & per-regime attribution from workstream D.
2. **Regime detection** — `app/regime/`: rule-based first (ADX + ATR%/realized-vol + EMA
   slope), upgrade to GMM/HMM (`scikit-learn` / `hmmlearn`). Tag signals/trades + dashboard.
3. **Meta-labeling filter** (highest priority) — train a gradient-boosted classifier on
   labeled history; open a trade only if `P(win) ≥ threshold`, and use the score for sizing.
   **Backtest with/without the filter; adopt only if it improves OOS Sharpe and reduces
   losers.** Wires into the scanner→paper path (filter before `open_from_signal`).
4. **Walk-forward auto-optimizer** — scheduled rolling re-optimization via the existing
   backtest engine; surface a **proposal** only when new params win out-of-sample.
5. **Adaptive allocation & auto-disable** — rolling per-(strategy, regime) performance →
   propose size multipliers, disable losers, re-enable when the regime turns favorable.
6. **LLM agent orchestrator** (Gemini/OpenRouter) — a periodic review reads stages 1–5,
   writes a plain-English assessment + concrete **proposals** to an `agent_proposals` table
   and an **"Agent" UI page** where the user Approves/Rejects. Approved proposals apply via
   existing levers (`active_strategies`, params, meta-label threshold, size multiplier). Full
   decision **journal + one-click revert**.

## Autonomy = propose-and-approve (decided)
The agent never trades freely; it pulls a fixed set of **bounded levers** within hard risk
caps, and a human confirms each change in the UI.

## Guardrails (from the "why ML funds fail" research — non-negotiable)
- **Paper-only; never auto-go-live** (live stays the gated Phase 5).
- Strict **out-of-sample / walk-forward** validation before a proposal is even shown;
  purged/embargoed CV to prevent leakage; triple-barrier labels.
- Agent levers are **bounded** (param ranges, max size multiplier, can't exceed risk caps).
- **Cold-start** from backtests; require ≥~100 trades before trusting the meta-model; edges
  must survive **±10% parameter perturbation**.
- Auto-flag overfitting **red flags** (win-rate >80%, profit factor >4, drawdown ≈ 0).
- Track **backtest-vs-paper divergence** and alert when live drifts from expectation.

## Free tools / deps
`scikit-learn`, optional `hmmlearn`, `joblib`; the existing backtest engine; the AI-provider
wrapper (NEXT plan workstream F); SQLite for the feature store + proposals. No paid services.

## Dependencies & data
Depends on **N2** (backtest realism), **N4** (robustness suite), **N7** (P&L attribution),
**N8** (AI wrapper). The agent improves as paper trades accumulate; it bootstraps from
backtest-generated labels until enough live-paper history exists.

## Success criteria (when built)
Meta-labeled paper trading shows **fewer loss-making trades and higher Sharpe** vs unfiltered,
confirmed out-of-sample; regime gating lowers drawdown; every agent change is traceable and
reversible.

## Realistic expectation
Improves *consistency and trade quality*, **not** a guaranteed profit engine. Live
underperforms backtest — that gap is monitored, not assumed away.

---

### Sources
- Meta-labeling: https://en.wikipedia.org/wiki/Meta-Labeling ,
  https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/
- "10 reasons most ML funds fail" (López de Prado):
  https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf
- RL limitations / backtest overfitting: https://arxiv.org/abs/2209.05559 ,
  https://www.blockchain-council.org/cryptocurrency/backtesting-ai-crypto-trading-strategies-avoiding-overfitting-lookahead-bias-data-leakage/
- Regime detection (HMM/GMM) + walk-forward:
  https://questdb.com/glossary/market-regime-detection-using-hidden-markov-models/ ,
  https://blog.quantinsti.com/walk-forward-optimization-introduction/
