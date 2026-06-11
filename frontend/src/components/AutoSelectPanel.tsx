import { useState } from 'react'
import { api, type AppConfig, type AutoSelectCandidate, type AutoSelectResult } from '../api/client'
import { Badge, Card } from './ui'

const METRICS = ['sharpe', 'return_pct', 'calmar', 'sortino', 'profit_factor']

/**
 * Auto-Select: screen every coin × strategy × chosen timeframe(s) over the
 * backtest window, rank with anti-overfit gates, and one-click promote winners.
 */
export default function AutoSelectPanel({
  config,
  start,
  end,
  leverage,
}: {
  config: AppConfig
  start: string
  end: string
  leverage: number
}) {
  const [timeframes, setTimeframes] = useState<string[]>(['1h'])
  const [metric, setMetric] = useState('sharpe')
  const [minTrades, setMinTrades] = useState(15)
  const [topN, setTopN] = useState(5)
  const [oosCheck, setOosCheck] = useState(true)
  const [beatBH, setBeatBH] = useState(false)
  const [res, setRes] = useState<AutoSelectResult | null>(null)
  const [loading, setLoading] = useState<'screen' | 'promote' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  function toggleTf(tf: string) {
    setTimeframes((p) => (p.includes(tf) ? p.filter((t) => t !== tf) : [...p, tf]))
  }

  async function run(promote: boolean) {
    if (timeframes.length === 0) {
      setError('Pick at least one timeframe.')
      return
    }
    setLoading(promote ? 'promote' : 'screen')
    setError(null)
    setNote(null)
    try {
      const r = await api.autoSelect({
        start, end, timeframes, metric, min_trades: minTrades,
        require_beat_buyhold: beatBH, oos_check: oosCheck, top_n: topN, promote, leverage,
      })
      setRes(r)
      if (promote) {
        setNote(
          r.promoted.length
            ? `Promoted ${r.promoted.length} strategy(ies) to live: ${r.promoted.map((p) => `${p.strategy}/${p.symbol} ${p.timeframe}`).join(', ')}.`
            : 'Nothing promoted — no candidates passed the gates.',
        )
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(null)
    }
  }

  return (
    <Card className="mb-6">
      <div className="font-medium mb-1">Auto-Select</div>
      <p className="text-sm text-slate-400 mb-4">
        Backtests every coin × strategy on the chosen timeframe(s) over the date range above,
        ranks by your metric, and gates out weak/overfit results. Promote the recommended top N
        straight to live signals.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <label className="text-sm">
          <span className="text-slate-400">Rank by</span>
          <select className="input" value={metric} onChange={(e) => setMetric(e.target.value)}>
            {METRICS.map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="text-slate-400">Min trades</span>
          <input className="input" type="number" min={1} value={minTrades}
            onChange={(e) => setMinTrades(Number(e.target.value))} />
        </label>
        <label className="text-sm">
          <span className="text-slate-400">Promote top N</span>
          <input className="input" type="number" min={1} max={20} value={topN}
            onChange={(e) => setTopN(Number(e.target.value))} />
        </label>
        <div className="text-sm">
          <span className="text-slate-400">Timeframes</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {config.timeframes.map((tf) => (
              <button key={tf} onClick={() => toggleTf(tf)}
                className={`px-2 py-1 rounded text-xs border ${
                  timeframes.includes(tf) ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-slate-700 text-slate-400'
                }`}>
                {tf}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4 mb-4">
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={oosCheck} onChange={(e) => setOosCheck(e.target.checked)} />
          Out-of-sample check (recommended)
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={beatBH} onChange={(e) => setBeatBH(e.target.checked)} />
          Must beat buy &amp; hold
        </label>
        <div className="flex gap-2 ml-auto">
          <button onClick={() => run(false)} disabled={loading !== null}
            className="px-4 py-1.5 rounded-md text-sm border border-slate-700 text-slate-200 hover:border-slate-500 disabled:opacity-40">
            {loading === 'screen' ? 'Screening…' : 'Screen'}
          </button>
          <button onClick={() => run(true)} disabled={loading !== null}
            className="px-4 py-1.5 rounded-md text-sm bg-emerald-500 text-slate-900 font-medium disabled:opacity-40">
            {loading === 'promote' ? 'Promoting…' : `Promote top ${topN}`}
          </button>
        </div>
      </div>

      {error && <p className="text-rose-400 text-sm mb-3">{error}</p>}
      {note && <p className="text-emerald-300 text-sm mb-3">{note}</p>}

      {res && (
        <>
          <div className="text-xs text-slate-500 mb-2">
            Tested {res.combos_tested} combos · {res.recommended_count} recommended · ranked by {res.metric}
            {oosCheck ? ' (out-of-sample)' : ''}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-slate-500 text-left">
                <tr>
                  <th className="py-1 pr-3"></th>
                  <th className="py-1 pr-3">Coin</th>
                  <th className="py-1 pr-3">TF</th>
                  <th className="py-1 pr-3">Strategy</th>
                  <th className="py-1 pr-3">Score</th>
                  <th className="py-1 pr-3">Return</th>
                  <th className="py-1 pr-3">Sharpe</th>
                  <th className="py-1 pr-3">Trades</th>
                  <th className="py-1 pr-3">Win%</th>
                  <th className="py-1 pr-3">Max DD</th>
                  <th className="py-1 pr-3">OOS</th>
                  <th className="py-1 pr-3">Notes</th>
                </tr>
              </thead>
              <tbody>
                {res.candidates.map((c: AutoSelectCandidate, i) => (
                  <tr key={i} className={`border-t border-slate-800 ${c.recommended ? 'bg-emerald-500/5' : ''}`}>
                    <td className="py-1 pr-3">{c.recommended ? <Badge tone="pos">✓</Badge> : ''}</td>
                    <td className="py-1 pr-3 font-medium">{c.symbol.replace('USDT', '')}</td>
                    <td className="py-1 pr-3">{c.timeframe}</td>
                    <td className="py-1 pr-3">{c.strategy}</td>
                    <td className="py-1 pr-3">{c.score ?? '—'}</td>
                    <td className={`py-1 pr-3 ${c.return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{c.return_pct}%</td>
                    <td className="py-1 pr-3">{c.sharpe}</td>
                    <td className="py-1 pr-3">{c.total_trades}</td>
                    <td className="py-1 pr-3">{c.win_rate}%</td>
                    <td className="py-1 pr-3 text-rose-300">{c.max_drawdown_pct}%</td>
                    <td className="py-1 pr-3">
                      {c.oos_held_up == null ? '—' : c.oos_held_up ? <Badge tone="pos">held</Badge> : <Badge tone="neg">failed</Badge>}
                    </td>
                    <td className="py-1 pr-3 text-xs text-slate-500">
                      {c.flags.length ? `⚠ ${c.flags.join(', ')}` : c.excluded_reasons.join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-600 mt-2">
            ✓ = passes all gates (enough trades, profitable{oosCheck ? ', holds out-of-sample' : ''}, no overfit flags).
            "Promote top N" promotes only recommended rows.
          </p>
        </>
      )}
    </Card>
  )
}
