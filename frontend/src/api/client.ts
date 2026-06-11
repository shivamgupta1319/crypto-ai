// Typed API client for the crypto-ai backend.
// In dev, Vite proxies /api -> FastAPI (see vite.config.ts).

export interface AppConfig {
  symbols: string[]
  timeframes: string[]
  initial_capital: number
  display_currency: string
  default_leverage: number
  max_leverage: number
  risk_per_trade_pct: number
}

export interface StrategyInfo {
  name: string
  description: string
  default_params: Record<string, unknown>
  suited_for: string[]
}

export interface Metrics {
  initial_capital: number
  final_equity: number
  net_pnl: number
  return_pct: number
  buy_hold_return_pct: number
  cagr_pct: number
  total_trades: number
  win_rate: number
  profit_factor: number | null
  avg_r: number
  expectancy_r: number
  max_drawdown_pct: number
  max_consecutive_losses: number
  avg_hold_hours: number
  exposure_pct: number
  sharpe: number
  sortino: number
  calmar: number | null
  sharpe_per_bar: number
}

export interface Trade {
  direction: 'LONG' | 'SHORT'
  entry: number
  exit: number
  qty: number
  pnl: number
  r: number
  reason: string
  entry_time: number
  exit_time: number
}

export interface EquityPoint {
  time: number
  equity: number
}

export interface StrategyResult {
  strategy: string
  metrics: Metrics
  equity_curve: EquityPoint[]
  trades: Trade[]
  benchmark_curve?: EquityPoint[]
}

export interface BacktestResponse {
  run_id?: number | null
  symbol: string
  timeframe: string
  start: string
  end: string
  candles: number
  results: StrategyResult[]
}

export interface BacktestRunSummary {
  id: number
  created_at: string
  symbol: string
  timeframe: string
  start: string
  end: string
  leverage: number
  risk_per_trade_pct: number
  candles: number
  strategies: string[]
  summary: Array<Record<string, number | string | null>>
}

export interface CurrentSetup {
  symbol: string
  timeframe: string
  strategy: string
  state: 'LONG' | 'SHORT' | 'FLAT'
  fresh: boolean
  actionable: boolean
  price: number
  entry: number | null
  stop: number | null
  target: number | null
  rr: number | null
  confidence: number
  bars_in_state: number
}

export interface ScanStatus {
  last_scan_at: string | null
  monitored: number
  interval_s: number
  alerts_enabled?: boolean
  price_stream?: boolean
}

export interface CoinSnapshot {
  symbol: string
  available: boolean
  price?: number
  change_24h_pct?: number
  regime?: string
  rsi?: number
  adx?: number
  ema_fast?: number
  ema_slow?: number
  macd_hist?: number
  macd_state?: 'bullish' | 'bearish'
  bb_pct?: number
  atr?: number
  atr_pct?: number
  vol_ratio?: number
}

export interface MarketOutlook {
  fear_greed: { value: number | null; classification: string; history: unknown[] }
  market_breadth: string
  direction_support?: string
  coins: CoinSnapshot[]
}

export interface ActiveStrategy {
  id: number
  symbol: string
  timeframe: string
  strategy: string
  params: Record<string, unknown>
  enabled: boolean
}

export interface LiveSignal {
  id: number
  symbol: string
  timeframe: string
  strategy: string
  direction: 'LONG' | 'SHORT'
  entry: number
  stop: number
  target: number
  rr?: number
  confidence: number
  bar_time: number
  created_at: string
}

export interface AccountSummary {
  initial_capital: number
  balance: number
  equity: number
  unrealized_pnl: number
  realized_pnl: number
  return_pct: number
  open_positions: number
  closed_trades: number
  win_rate: number
  kill_switch: boolean
  display_currency: string
}

export interface OpenPosition {
  id: number
  symbol: string
  strategy: string
  direction: 'LONG' | 'SHORT'
  qty: number
  leverage: number
  entry_price: number
  stop: number
  target: number
  current_price: number
  unrealized_pnl: number
  opened_at: string
}

export interface ClosedTrade {
  id: number
  symbol: string
  strategy: string
  direction: 'LONG' | 'SHORT'
  qty: number
  entry_price: number
  exit_price: number | null
  pnl: number
  fees: number
  opened_at: string
  closed_at: string | null
}

export interface StrategyAttribution {
  strategy: string
  trades: number
  net_pnl: number
  win_rate: number
  avg_pnl: number
  profit_factor: number | null
}

export interface RiskPosition {
  id: number
  symbol: string
  direction: 'LONG' | 'SHORT'
  leverage: number
  notional: number
  margin: number
  liquidation_price: number
}

export interface RiskView {
  equity: number
  gross_exposure: number
  net_exposure: number
  gross_exposure_pct: number
  margin_used: number
  margin_used_pct: number
  concentration_pct: Record<string, number>
  correlation_warning: boolean
  positions: RiskPosition[]
}

export interface NewsItem {
  source: string
  title: string
  link: string
  summary: string
  published: string
  published_ts: number | null
  coins: string[]
  sentiment: 'positive' | 'negative' | 'neutral'
}

export interface AgentProposal {
  id: number
  created_at: string | null
  kind: string
  title: string
  rationale: string
  payload: Record<string, unknown>
  confidence: number
  status: 'pending' | 'approved' | 'rejected' | 'reverted'
  decided_at: string | null
}

export interface AgentOverview {
  enabled: boolean
  ai_enabled: boolean
  meta_label_enabled: boolean
  meta_label_threshold: number
  dataset: { total: number; by_strategy: Array<{ strategy: string; samples: number; win_rate: number; avg_r: number }> }
  model: { models: Array<Record<string, unknown>>; min_samples?: number }
  allocation: {
    strategies: Array<{
      strategy: string; trades: number; net_pnl: number; win_rate: number
      avg_pnl: number; profit_factor: number | null; active: boolean; enabled: boolean
      regimes: Record<string, { win_rate: number; samples: number }>
    }>
  }
  levers: { size_multipliers: Record<string, number> }
  pending_proposals: AgentProposal[]
  recent_proposals: AgentProposal[]
  narrative: string | null
}

export interface RegimeView {
  regimes: Array<{ symbol: string; regime: string; label: string }>
}

export interface SettingField {
  key: string
  kind: 'float' | 'int' | 'bool' | 'symbols' | 'timeframes'
  label: string
  min: number | null
  max: number | null
  note: string | null
}

export interface SettingsView {
  values: Record<string, number | boolean | string[]>
  fields: SettingField[]
}

export interface DerivativeCoin {
  symbol: string
  available: boolean
  funding_rate_pct: number | null
  funding_apr_pct: number | null
  next_funding_time: number | null
  open_interest: number | null
  long_short_ratio: number | null
  long_pct: number | null
  short_pct: number | null
}

export interface GlobalStats {
  total_market_cap_usd: number | null
  btc_dominance_pct: number
  eth_dominance_pct: number
  market_cap_change_24h_pct: number
}

export interface DerivativesView {
  coins: DerivativeCoin[]
  global: GlobalStats | null
}

export interface CorrelationView {
  symbols: string[]
  matrix: number[][]
  avg_correlation?: number | null
  available: boolean
}

export interface AiStatus {
  enabled: boolean
  provider: string | null
  model: string | null
}

export interface AiResponse extends AiStatus {
  text: string | null
  hint?: string
  generated_at?: number
  cached?: boolean
}

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error((detail as { detail?: string }).detail ?? `Request failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  getConfig: () => http<AppConfig>('/api/config'),
  getStrategies: () => http<StrategyInfo[]>('/api/strategies'),
  getOutlook: () => http<MarketOutlook>('/api/market/outlook'),
  getDerivatives: () => http<DerivativesView>('/api/market/derivatives'),
  getCorrelation: (timeframe = '1h') =>
    http<CorrelationView>(`/api/market/correlation?timeframe=${timeframe}`),
  getActive: () => http<ActiveStrategy[]>('/api/strategies/active'),
  runBacktest: (body: {
    symbol: string
    timeframe: string
    start: string
    end: string
    strategies: string[]
    leverage?: number
    risk_per_trade_pct?: number
  }) => http<BacktestResponse>('/api/backtest', { method: 'POST', body: JSON.stringify(body) }),
  promote: (body: { symbol: string; timeframe: string; strategy: string }) =>
    http<ActiveStrategy>('/api/strategies/promote', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteActive: (id: number) =>
    http<{ deleted: boolean }>(`/api/strategies/active/${id}`, { method: 'DELETE' }),
  getCurrentSetups: (scope: 'active' | 'all' = 'active') =>
    http<{ scope: string; setups: CurrentSetup[]; count: number }>(
      `/api/signals/current?scope=${scope}`,
    ),
  getScanStatus: () => http<ScanStatus>('/api/signals/status'),
  getBacktestRuns: (limit = 50) => http<BacktestRunSummary[]>(`/api/backtest/runs?limit=${limit}`),
  getBacktestRun: (id: number) => http<BacktestResponse>(`/api/backtest/runs/${id}`),
  getSignals: (limit = 50) => http<LiveSignal[]>(`/api/signals?limit=${limit}`),
  scanNow: () =>
    http<{ new_signals: LiveSignal[]; count: number; opened: number; closed: number }>(
      '/api/signals/scan',
      { method: 'POST' },
    ),
  getSummary: () => http<AccountSummary>('/api/portfolio/summary'),
  getPositions: () => http<OpenPosition[]>('/api/portfolio/positions'),
  getTrades: (limit = 100) => http<ClosedTrade[]>(`/api/portfolio/trades?limit=${limit}`),
  getPortfolioEquity: () => http<EquityPoint[]>('/api/portfolio/equity-curve'),
  getAttribution: () => http<StrategyAttribution[]>('/api/portfolio/attribution'),
  getRisk: () => http<RiskView>('/api/portfolio/risk'),
  resetAccount: () => http<{ deleted: number }>('/api/portfolio/reset', { method: 'POST' }),
  closePosition: (id: number) =>
    http<{ id: number; pnl: number }>(`/api/portfolio/positions/${id}/close`, { method: 'POST' }),
  getNews: (coin?: string, limit = 40) =>
    http<NewsItem[]>(`/api/news?limit=${limit}${coin ? `&coin=${coin}` : ''}`),
  // Adaptive Intelligence Layer (N10) — advisory; proposals need human approval.
  getAgentOverview: () => http<AgentOverview>('/api/agent/overview'),
  getAgentRegime: () => http<RegimeView>('/api/agent/regime'),
  agentReview: () => http<{ created: number; pending: number; narrative: string | null }>(
    '/api/agent/review', { method: 'POST' }),
  agentBuildDataset: (body: { strategy: string; symbol: string; timeframe: string; start: string; end: string }) =>
    http<{ built: number; inserted: number }>('/api/agent/dataset/build', { method: 'POST', body: JSON.stringify(body) }),
  agentTrain: (strategy: string | null) =>
    http<Record<string, unknown>>('/api/agent/model/train', { method: 'POST', body: JSON.stringify({ strategy }) }),
  agentApprove: (id: number) => http<AgentProposal>(`/api/agent/proposals/${id}/approve`, { method: 'POST' }),
  agentReject: (id: number) => http<AgentProposal>(`/api/agent/proposals/${id}/reject`, { method: 'POST' }),
  agentRevert: (id: number) => http<AgentProposal>(`/api/agent/proposals/${id}/revert`, { method: 'POST' }),
  // Settings (runtime-editable risk/leverage/universe).
  getSettings: () => http<SettingsView>('/api/settings'),
  updateSettings: (values: Record<string, number | boolean | string[]>) =>
    http<SettingsView>('/api/settings', { method: 'PUT', body: JSON.stringify({ values }) }),
  resetSettings: () => http<SettingsView>('/api/settings/reset', { method: 'POST' }),
  // AI layer (advisory only — never trades).
  getAiStatus: () => http<AiStatus>('/api/ai/status'),
  aiCommentary: (refresh = false) =>
    http<AiResponse>(`/api/ai/commentary?refresh=${refresh}`, { method: 'POST' }),
  aiAsk: (question: string) =>
    http<AiResponse>('/api/ai/ask', { method: 'POST', body: JSON.stringify({ question }) }),
  aiExplainBacktest: (run_id: number) =>
    http<AiResponse>('/api/ai/backtest-explain', {
      method: 'POST',
      body: JSON.stringify({ run_id }),
    }),
  // Robustness suite (all share the RobustnessRequest body shape).
  sweep: (body: RobustnessRequest) => http<SweepResult>('/api/backtest/sweep', { method: 'POST', body: JSON.stringify(body) }),
  oos: (body: RobustnessRequest) => http<OosResult>('/api/backtest/oos', { method: 'POST', body: JSON.stringify(body) }),
  walkForward: (body: RobustnessRequest) => http<WalkForwardResult>('/api/backtest/walkforward', { method: 'POST', body: JSON.stringify(body) }),
  monteCarlo: (body: RobustnessRequest) => http<MonteCarloResult>('/api/backtest/montecarlo', { method: 'POST', body: JSON.stringify(body) }),
}

export interface RobustnessRequest {
  symbol: string
  timeframe: string
  start: string
  end: string
  strategy: string
  param_grid?: Record<string, Array<number>>
  metric?: string
  leverage?: number
  train_frac?: number
  folds?: number
  n_iter?: number
  params?: Record<string, number>
}

export interface SweepRow {
  params: Record<string, number>
  return_pct: number
  sharpe: number
  max_drawdown_pct: number
  win_rate: number
  profit_factor: number | null
  total_trades: number
}
export interface SweepResult {
  metric: string
  combos_tested: number
  results: SweepRow[]
  best: SweepRow
  heatmap: {
    x_param: string; y_param: string
    x_values: number[]; y_values: number[]
    metric: string; matrix: (number | null)[][]
  } | null
  perturbation: Array<{ param: string; base: number; down: number; up: number; fragile: boolean }>
  robust: boolean | null
}
export interface OosResult {
  best_params: Record<string, number>
  train: Metrics
  test: Metrics
  degradation_pct: number
  held_up: boolean
}
export interface WalkForwardResult {
  windows: Array<{ window: number; test_return_pct: number; test_sharpe: number; test_trades: number }>
  consistency_pct: number
  avg_test_return_pct: number
  note?: string
}
export interface MonteCarloResult {
  trades: number
  iterations: number
  return_p5: number
  return_p50: number
  return_p95: number
  max_drawdown_p50: number
  max_drawdown_p95: number
  prob_profit_pct: number
}

// WebSocket URL for the live signal feed (proxied by Vite in dev).
export function signalsWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/api/signals/ws`
}
