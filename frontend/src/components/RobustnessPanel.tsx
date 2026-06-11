import { useState } from 'react'
import {
  api,
  type MonteCarloResult,
  type OosResult,
  type StrategyInfo,
  type SweepResult,
  type WalkForwardResult,
} from '../api/client'
import { Badge, Card, Stat } from './ui'

// Build a small sweep grid from a strategy's first ~2 numeric params (±20%).
function buildGrid(strat: StrategyInfo): Record<string, number[]> {
  const grid: Record<string, number[]> = {}
  let picked = 0
  for (const [k, v] of Object.entries(strat.default_params)) {
    if (typeof v !== 'number' || picked >= 2) continue
    const isInt = Number.isInteger(v)
    const vals = isInt
      ? [Math.max(1, Math.round(v * 0.8)), v, Math.round(v * 1.2)]
      : [+(v * 0.8).toFixed(4), v, +(v * 1.2).toFixed(4)]
    grid[k] = [...new Set(vals)]
    picked++
  }
  return grid
}

function heatColor(v: number | null, lo: number, hi: number): string {
  if (v === null) return '#1e293b'
  const t = hi === lo ? 0.5 : (v - lo) / (hi - lo)
  const r = Math.round(220 - t * 180)
  const g = Math.round(40 + t * 170)
  return `rgb(${r},${g},80)`
}

export default function RobustnessPanel({
  symbol, timeframe, start, end, leverage, strategies,
}: {
  symbol: string; timeframe: string; start: string; end: string
  leverage: number; strategies: StrategyInfo[]
}) {
  const [strategy, setStrategy] = useState(strategies[0]?.name ?? '')
  const [metric, setMetric] = useState('sharpe')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sweep, setSweep] = useState<SweepResult | null>(null)
  const [oos, setOos] = useState<OosResult | null>(null)
  const [wf, setWf] = useState<WalkForwardResult | null>(null)
  const [mc, setMc] = useState<MonteCarloResult | null>(null)

  const strat = strategies.find((s) => s.name === strategy)
  const grid = strat ? buildGrid(strat) : {}
  const sweptParams = Object.keys(grid)

  async function run() {
    if (!strat) return
    setLoading(true); setError(null); setSweep(null); setOos(null); setWf(null); setMc(null)
    const base = { symbol, timeframe, start, end, strategy, metric, leverage, param_grid: grid }
    try {
      const sw = await api.sweep(base)
      setSweep(sw)
      const [o, w, m] = await Promise.all([
        api.oos(base).catch(() => null),
        api.walkForward({ ...base, folds: 5 }).catch(() => null),
        api.monteCarlo({ symbol, timeframe, start, end, strategy, params: sw.best?.params }).catch(() => null),
      ])
      setOos(o); setWf(w); setMc(m)
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="mb-6">
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <label className="text-sm">
          <span className="text-slate-400">Strategy</span>
          <select className="input" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            {strategies.map((s) => <option key={s.name}>{s.name}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-slate-400">Optimize for</span>
          <select className="input" value={metric} onChange={(e) => setMetric(e.target.value)}>
            <option value="sharpe">Sharpe</option>
            <option value="return_pct">Return %</option>
            <option value="profit_factor">Profit factor</option>
          </select>
        </label>
        <button
          onClick={run}
          disabled={loading || !strat}
          className="px-4 py-2 rounded-md bg-emerald-500 text-slate-900 font-medium disabled:opacity-40"
        >
          {loading ? 'Running…' : 'Run robustness'}
        </button>
        <span className="text-xs text-slate-500">
          {symbol} {timeframe} · sweeping: {sweptParams.join(', ') || '(no numeric params)'}
        </span>
      </div>
      {error && <p className="text-rose-400 text-sm mb-3">{error}</p>}

      {/* Parameter sweep + perturbation */}
      {sweep && (
        <div className="mb-5">
          <div className="flex items-center gap-3 mb-2">
            <span className="font-medium">Parameter sweep ({sweep.combos_tested} combos)</span>
            {sweep.robust !== null && (
              <Badge tone={sweep.robust ? 'pos' : 'warn'}>
                {sweep.robust ? 'robust to ±10%' : 'fragile to ±10%'}
              </Badge>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-slate-500 text-left">
                <tr>
                  <th className="py-1 pr-4">Params</th>
                  <th className="py-1 pr-4">Return</th>
                  <th className="py-1 pr-4">Sharpe</th>
                  <th className="py-1 pr-4">Max DD</th>
                  <th className="py-1 pr-4">Win%</th>
                  <th className="py-1 pr-4">Trades</th>
                </tr>
              </thead>
              <tbody>
                {sweep.results.slice(0, 8).map((r, i) => (
                  <tr key={i} className={`border-t border-slate-800 ${i === 0 ? 'text-emerald-300' : ''}`}>
                    <td className="py-1 pr-4">{Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(', ')}</td>
                    <td className="py-1 pr-4">{r.return_pct}%</td>
                    <td className="py-1 pr-4">{r.sharpe}</td>
                    <td className="py-1 pr-4 text-rose-300">{r.max_drawdown_pct}%</td>
                    <td className="py-1 pr-4">{r.win_rate}%</td>
                    <td className="py-1 pr-4">{r.total_trades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {sweep.heatmap && (
            <div className="mt-3">
              <div className="text-xs text-slate-500 mb-1">
                Heatmap of {sweep.heatmap.metric} ({sweep.heatmap.x_param} × {sweep.heatmap.y_param})
              </div>
              <HeatmapGrid hm={sweep.heatmap} />
            </div>
          )}

          {sweep.perturbation.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3 text-xs">
              {sweep.perturbation.map((p) => (
                <span key={p.param} className={`px-2 py-1 rounded ${p.fragile ? 'bg-amber-500/15 text-amber-300' : 'bg-slate-700/40 text-slate-300'}`}>
                  {p.param}: {p.down} / {p.base} / {p.up} {p.fragile ? '⚠' : '✓'}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Out-of-sample */}
      {oos && (
        <div className="mb-5">
          <div className="flex items-center gap-3 mb-2">
            <span className="font-medium">Out-of-sample (train 70% → test 30%)</span>
            <Badge tone={oos.held_up ? 'pos' : 'neg'}>{oos.held_up ? 'held up' : 'broke down'}</Badge>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Train return" value={`${oos.train.return_pct}%`} tone={oos.train.return_pct >= 0 ? 'pos' : 'neg'} />
            <Stat label="Test return" value={`${oos.test.return_pct}%`} tone={oos.test.return_pct >= 0 ? 'pos' : 'neg'} />
            <Stat label="Test Sharpe" value={oos.test.sharpe} />
            <Stat label="Degradation" value={`${oos.degradation_pct}%`} tone="neg" />
          </div>
        </div>
      )}

      {/* Walk-forward */}
      {wf && (
        <div className="mb-5">
          <div className="flex items-center gap-3 mb-2">
            <span className="font-medium">Walk-forward</span>
            {wf.windows.length > 0 && (
              <Badge tone={wf.consistency_pct >= 60 ? 'pos' : 'warn'}>
                {wf.consistency_pct}% windows positive
              </Badge>
            )}
          </div>
          {wf.windows.length === 0 ? (
            <p className="text-slate-500 text-sm">{wf.note ?? 'No windows.'}</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {wf.windows.map((w) => (
                <div key={w.window} className="px-3 py-2 rounded bg-slate-800/60 text-sm">
                  <div className="text-xs text-slate-500">Window {w.window}</div>
                  <div className={w.test_return_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'}>
                    {w.test_return_pct}% · {w.test_trades} trades
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Monte Carlo */}
      {mc && (
        <div>
          <div className="font-medium mb-2">Monte Carlo ({mc.iterations} resamples of {mc.trades} trades)</div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Stat label="Return p5" value={`${mc.return_p5}%`} tone="neg" />
            <Stat label="Return p50" value={`${mc.return_p50}%`} />
            <Stat label="Return p95" value={`${mc.return_p95}%`} tone="pos" />
            <Stat label="Worst-5% drawdown" value={`${mc.max_drawdown_p95}%`} tone="neg" />
            <Stat label="Prob. profit" value={`${mc.prob_profit_pct}%`} />
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Size risk to the worst-5% drawdown, not the lucky path.
          </p>
        </div>
      )}
    </Card>
  )
}

function HeatmapGrid({ hm }: { hm: NonNullable<SweepResult['heatmap']> }) {
  const flat = hm.matrix.flat().filter((v): v is number => v !== null)
  const lo = Math.min(...flat, 0)
  const hi = Math.max(...flat, 0)
  return (
    <div className="inline-block">
      <div className="flex">
        <div className="w-16" />
        {hm.x_values.map((xv) => (
          <div key={xv} className="w-14 text-center text-xs text-slate-500">{xv}</div>
        ))}
      </div>
      {hm.matrix.map((row, ri) => (
        <div key={ri} className="flex items-center">
          <div className="w-16 text-right pr-2 text-xs text-slate-500">{hm.y_values[ri]}</div>
          {row.map((v, ci) => (
            <div
              key={ci}
              className="w-14 h-9 flex items-center justify-center text-xs text-slate-900 font-medium"
              style={{ background: heatColor(v, lo, hi) }}
              title={`${hm.x_param}=${hm.x_values[ci]}, ${hm.y_param}=${hm.y_values[ri]}`}
            >
              {v === null ? '—' : v.toFixed(2)}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
