import { useEffect, useMemo, useState } from 'react'
import {
  api,
  type AppConfig,
  type BacktestResponse,
  type BacktestRunSummary,
  type StrategyInfo,
  type StrategyResult,
} from '../api/client'
import { Badge, Card, PageTitle, Stat } from '../components/ui'
import EquityChart from '../components/EquityChart'
import RobustnessPanel from '../components/RobustnessPanel'
import type { AiResponse } from '../api/client'

const COLORS = ['#34d399', '#60a5fa', '#f472b6', '#fbbf24', '#a78bfa', '#22d3ee']

function fmt(n: number | null | undefined, suffix = '') {
  if (n === null || n === undefined) return '—'
  return `${n}${suffix}`
}

export default function Backtest() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('1h')
  const [start, setStart] = useState('2024-01-01')
  const [end, setEnd] = useState('2024-06-01')
  const [selected, setSelected] = useState<string[]>([])
  const [leverage, setLeverage] = useState(3)
  const [result, setResult] = useState<BacktestResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [promoted, setPromoted] = useState<Record<string, boolean>>({})
  const [showHistory, setShowHistory] = useState(false)
  const [runs, setRuns] = useState<BacktestRunSummary[]>([])
  const [showRobustness, setShowRobustness] = useState(false)
  const [explain, setExplain] = useState<AiResponse | null>(null)
  const [explaining, setExplaining] = useState(false)

  useEffect(() => {
    api.getConfig().then((c) => {
      setConfig(c)
      setSymbol(c.symbols[0])
      setLeverage(c.default_leverage)
    })
    api.getStrategies().then((s) => {
      setStrategies(s)
      setSelected([s[0]?.name].filter(Boolean) as string[])
    })
  }, [])

  function toggle(name: string) {
    setSelected((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]))
  }

  async function run() {
    setError(null)
    setRunning(true)
    setResult(null)
    setPromoted({})
    setExplain(null)
    try {
      const res = await api.runBacktest({ symbol, timeframe, start, end, strategies: selected, leverage })
      setResult(res)
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setRunning(false)
    }
  }

  async function promote(r: StrategyResult) {
    try {
      await api.promote({ symbol, timeframe, strategy: r.strategy })
      setPromoted((p) => ({ ...p, [r.strategy]: true }))
    } catch (e) {
      setError(String((e as Error).message))
    }
  }

  async function toggleHistory() {
    const next = !showHistory
    setShowHistory(next)
    if (next) {
      try {
        setRuns(await api.getBacktestRuns())
      } catch (e) {
        setError(String((e as Error).message))
      }
    }
  }

  async function loadRun(id: number) {
    try {
      const r = await api.getBacktestRun(id)
      setResult(r)
      setSymbol(r.symbol)
      setTimeframe(r.timeframe)
      setPromoted({})
      setExplain(null)
      setShowHistory(false)
    } catch (e) {
      setError(String((e as Error).message))
    }
  }

  async function explainRun() {
    if (!result?.run_id) return
    setExplaining(true)
    try {
      setExplain(await api.aiExplainBacktest(result.run_id))
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setExplaining(false)
    }
  }

  const chartSeries = useMemo(() => {
    const series = (result?.results ?? []).map((r, i) => ({
      label: r.strategy,
      color: COLORS[i % COLORS.length],
      data: r.equity_curve,
    }))
    // Overlay buy-&-hold (same for all strategies in the run) as a grey baseline.
    const bench = result?.results?.[0]?.benchmark_curve
    if (bench && bench.length) series.push({ label: 'buy & hold', color: '#64748b', data: bench })
    return series
  }, [result])

  return (
    <div>
      <div className="flex items-center justify-between">
        <PageTitle
          title="Backtesting"
          subtitle="Run strategies on real Binance history, compare results, and promote winners to live signals"
        />
        <div className="flex gap-2">
          <button
            onClick={() => setShowRobustness((v) => !v)}
            className="px-3 py-1.5 rounded-md text-sm border border-slate-700 text-slate-300 hover:border-slate-500"
          >
            {showRobustness ? 'Hide robustness' : 'Robustness'}
          </button>
          <button
            onClick={toggleHistory}
            className="px-3 py-1.5 rounded-md text-sm border border-slate-700 text-slate-300 hover:border-slate-500"
          >
            {showHistory ? 'Hide history' : 'History'}
          </button>
        </div>
      </div>

      {showRobustness && config && strategies.length > 0 && (
        <RobustnessPanel
          symbol={symbol}
          timeframe={timeframe}
          start={start}
          end={end}
          leverage={leverage}
          strategies={strategies}
        />
      )}

      {showHistory && (
        <Card className="mb-6">
          <div className="font-medium mb-3">Saved Backtest Runs</div>
          {runs.length === 0 ? (
            <p className="text-slate-500 text-sm">No saved runs yet — run a backtest and it'll appear here.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-slate-500 text-left">
                  <tr>
                    <th className="py-1 pr-4">When</th>
                    <th className="py-1 pr-4">Symbol</th>
                    <th className="py-1 pr-4">TF</th>
                    <th className="py-1 pr-4">Range</th>
                    <th className="py-1 pr-4">Lev</th>
                    <th className="py-1 pr-4">Strategies</th>
                    <th className="py-1 pr-4">Best return</th>
                    <th className="py-1 pr-4"></th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const best = r.summary.reduce<number | null>((acc, s) => {
                      const v = typeof s.return_pct === 'number' ? s.return_pct : null
                      return v !== null && (acc === null || v > acc) ? v : acc
                    }, null)
                    return (
                      <tr key={r.id} className="border-t border-slate-800">
                        <td className="py-1 pr-4 text-slate-500">{new Date(r.created_at).toLocaleString()}</td>
                        <td className="py-1 pr-4 font-medium">{r.symbol}</td>
                        <td className="py-1 pr-4">{r.timeframe}</td>
                        <td className="py-1 pr-4 text-slate-500">{r.start} → {r.end}</td>
                        <td className="py-1 pr-4">{r.leverage}x</td>
                        <td className="py-1 pr-4 text-slate-400">{r.strategies.join(', ')}</td>
                        <td className={`py-1 pr-4 ${(best ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {best === null ? '—' : `${best}%`}
                        </td>
                        <td className="py-1 pr-4">
                          <button onClick={() => loadRun(r.id)} className="text-blue-300 hover:underline">
                            View
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Card className="mb-6">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
          <label className="text-sm">
            <span className="text-slate-400">Symbol</span>
            <select className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
              {config?.symbols.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-slate-400">Timeframe</span>
            <select className="input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              {config?.timeframes.map((t) => <option key={t}>{t}</option>)}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-slate-400">Start</span>
            <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="text-sm">
            <span className="text-slate-400">End</span>
            <input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <label className="text-sm">
            <span className="text-slate-400">Leverage ({leverage}x)</span>
            <input
              className="input"
              type="range"
              min={1}
              max={config?.max_leverage ?? 5}
              step={1}
              value={leverage}
              onChange={(e) => setLeverage(Number(e.target.value))}
            />
          </label>
        </div>

        <div className="mb-4">
          <span className="text-slate-400 text-sm">Strategies</span>
          <span className="ml-2"><Badge tone="neutral">Long &amp; Short</Badge></span>
          <div className="flex flex-wrap gap-2 mt-2">
            {strategies.map((s) => (
              <button
                key={s.name}
                onClick={() => toggle(s.name)}
                title={s.description}
                className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
                  selected.includes(s.name)
                    ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300'
                    : 'border-slate-700 text-slate-400 hover:border-slate-500'
                }`}
              >
                {s.name}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={run}
          disabled={running || selected.length === 0}
          className="px-4 py-2 rounded-md bg-emerald-500 text-slate-900 font-medium disabled:opacity-40"
        >
          {running ? 'Running…' : 'Run Backtest'}
        </button>
        {error && <p className="text-rose-400 mt-3 text-sm">{error}</p>}
      </Card>

      {result && (
        <>
          <Card className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <span className="font-medium">
                Equity Curves · {result.symbol} {result.timeframe} · {result.candles} candles
              </span>
              {result.run_id != null && (
                <button
                  onClick={explainRun}
                  disabled={explaining}
                  className="px-3 py-1.5 rounded-md text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 font-medium"
                >
                  {explaining ? 'Analyzing…' : '✨ Explain with AI'}
                </button>
              )}
            </div>
            {explain && (
              <div className="mb-4 rounded-lg border border-indigo-500/30 bg-indigo-500/5 p-3">
                {explain.enabled ? (
                  <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">{explain.text}</p>
                ) : (
                  <p className="text-sm text-slate-400">{explain.hint}</p>
                )}
              </div>
            )}
            <EquityChart series={chartSeries} />
            <div className="flex gap-4 mt-3 text-sm">
              {chartSeries.map((s) => (
                <span key={s.label} className="flex items-center gap-1">
                  <span className="w-3 h-0.5 inline-block" style={{ background: s.color }} /> {s.label}
                </span>
              ))}
            </div>
          </Card>

          <div className="space-y-4">
            {result.results.map((r) => (
              <Card key={r.strategy}>
                <div className="flex items-center justify-between mb-4">
                  <span className="font-semibold text-lg">{r.strategy}</span>
                  <button
                    onClick={() => promote(r)}
                    disabled={promoted[r.strategy]}
                    className="px-3 py-1.5 rounded-md text-sm bg-blue-500/20 text-blue-300 border border-blue-500/40 disabled:opacity-50"
                  >
                    {promoted[r.strategy] ? '✓ Promoted to live' : 'Promote to live'}
                  </button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                  <Stat
                    label="Return"
                    value={fmt(r.metrics.return_pct, '%')}
                    tone={r.metrics.return_pct >= 0 ? 'pos' : 'neg'}
                  />
                  <Stat
                    label="vs Buy&Hold"
                    value={fmt(Math.round((r.metrics.return_pct - r.metrics.buy_hold_return_pct) * 100) / 100, '%')}
                    tone={r.metrics.return_pct >= r.metrics.buy_hold_return_pct ? 'pos' : 'neg'}
                  />
                  <Stat label="CAGR" value={fmt(r.metrics.cagr_pct, '%')} />
                  <Stat label="Net P&L" value={fmt(r.metrics.net_pnl)} tone={r.metrics.net_pnl >= 0 ? 'pos' : 'neg'} />
                  <Stat label="Trades" value={r.metrics.total_trades} />
                  <Stat label="Win Rate" value={fmt(r.metrics.win_rate, '%')} />
                  <Stat label="Profit Factor" value={fmt(r.metrics.profit_factor)} />
                  <Stat label="Expectancy R" value={fmt(r.metrics.expectancy_r)} />
                  <Stat label="Sharpe (ann)" value={fmt(r.metrics.sharpe)} />
                  <Stat label="Sortino" value={fmt(r.metrics.sortino)} />
                  <Stat label="Calmar" value={fmt(r.metrics.calmar)} />
                  <Stat label="Max DD" value={fmt(r.metrics.max_drawdown_pct, '%')} tone="neg" />
                  <Stat label="Max Consec L" value={r.metrics.max_consecutive_losses} />
                  <Stat label="Avg Hold (h)" value={fmt(r.metrics.avg_hold_hours)} />
                  <Stat label="Exposure" value={fmt(r.metrics.exposure_pct, '%')} />
                </div>

                {r.trades.length > 0 && (
                  <details className="mt-4">
                    <summary className="text-sm text-slate-400 cursor-pointer">
                      Trade log ({r.trades.length})
                    </summary>
                    <div className="overflow-x-auto mt-2">
                      <table className="w-full text-sm">
                        <thead className="text-slate-500 text-left">
                          <tr>
                            <th className="py-1 pr-4">Dir</th>
                            <th className="py-1 pr-4">Entry</th>
                            <th className="py-1 pr-4">Exit</th>
                            <th className="py-1 pr-4">P&L</th>
                            <th className="py-1 pr-4">R</th>
                            <th className="py-1 pr-4">Reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {r.trades.slice(0, 100).map((t, i) => (
                            <tr key={i} className="border-t border-slate-800">
                              <td className="py-1 pr-4">
                                <Badge tone={t.direction === 'LONG' ? 'pos' : 'neg'}>{t.direction}</Badge>
                              </td>
                              <td className="py-1 pr-4">{t.entry}</td>
                              <td className="py-1 pr-4">{t.exit}</td>
                              <td className={`py-1 pr-4 ${t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {t.pnl}
                              </td>
                              <td className="py-1 pr-4">{t.r}</td>
                              <td className="py-1 pr-4 text-slate-500">{t.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                )}
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
