import { useState } from 'react'
import { api, type AutoSelectCandidate, type AutoSelectResult } from '../api/client'
import { Badge, Card } from './ui'

function oneYearAgo(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().slice(0, 10)
}
const today = () => new Date().toISOString().slice(0, 10)

/**
 * One-click Auto-Select: backtests every coin × strategy × timeframe over the
 * last year, scores them on a balanced metric (return, drawdown, confidence),
 * auto-promotes the best per coin, and lists the picks with a Remove action.
 */
export default function AutoSelectPanel() {
  const [res, setRes] = useState<AutoSelectResult | null>(null)
  const [picks, setPicks] = useState<AutoSelectCandidate[]>([])
  const [loading, setLoading] = useState(false)
  const [removing, setRemoving] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  async function run() {
    setLoading(true)
    setError(null)
    try {
      const r = await api.autoSelect({
        start: oneYearAgo(),
        end: today(),
        metric: 'composite',
        oos_check: true,
        min_trades: 15,
        per_coin_top: 2, // best ~2 strategies per coin
        promote: true,
      })
      setRes(r)
      setPicks(r.selected)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function remove(p: AutoSelectCandidate) {
    if (p.active_id == null) return
    setRemoving(p.active_id)
    try {
      await api.deleteActive(p.active_id)
      setPicks((cur) => cur.filter((x) => x.active_id !== p.active_id)) // instant
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRemoving(null)
    }
  }

  return (
    <Card className="mb-6">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <div className="font-medium">Auto-Select</div>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">
            One click: backtests <strong>every coin × strategy</strong> across the swing timeframes
            (15m / 1h / 4h / 1d) over the last year, scores each on a balanced metric (return,
            drawdown, win-rate, risk-adjusted return), validates out-of-sample, and{' '}
            <strong>auto-promotes the best per coin</strong> to live signals. Remove any you don't want.
          </p>
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="shrink-0 px-4 py-2 rounded-md text-sm bg-emerald-500 text-slate-900 font-medium disabled:opacity-50 inline-flex items-center gap-2"
        >
          {loading && (
            <span className="inline-block w-3.5 h-3.5 border-2 border-slate-900/30 border-t-slate-900 rounded-full animate-spin" />
          )}
          {loading ? 'Analyzing…' : 'Auto-Select'}
        </button>
      </div>

      {loading && (
        <p className="text-xs text-slate-500 mb-2">
          Running the full sweep over a year of data — the first run can take a minute or two while
          candles download; later runs are fast (cached).
        </p>
      )}
      {error && <p className="text-rose-400 text-sm mb-3">{error}</p>}

      {res && (
        <>
          <div className="text-xs text-slate-500 mb-2">
            Tested {res.combos_tested} combos · {res.recommended_count} passed the gates · auto-selected{' '}
            {picks.length} (scored by {res.metric}, out-of-sample validated).
          </div>

          {picks.length === 0 ? (
            <p className="text-slate-400 text-sm">
              Nothing cleared the quality gates (enough trades, profitable, holds out-of-sample, no
              overfit flags) over the last year. Nothing was promoted.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-slate-500 text-left">
                  <tr>
                    <th className="py-1 pr-3">Coin</th>
                    <th className="py-1 pr-3">Strategy</th>
                    <th className="py-1 pr-3">TF</th>
                    <th className="py-1 pr-3">Return</th>
                    <th className="py-1 pr-3">Max DD</th>
                    <th className="py-1 pr-3">Win%</th>
                    <th className="py-1 pr-3">Sharpe</th>
                    <th className="py-1 pr-3">Trades</th>
                    <th className="py-1 pr-3">OOS</th>
                    <th className="py-1 pr-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {picks.map((p) => (
                    <tr key={p.active_id ?? `${p.symbol}-${p.timeframe}-${p.strategy}`} className="border-t border-slate-800">
                      <td className="py-1 pr-3 font-medium">{p.symbol.replace('USDT', '')}</td>
                      <td className="py-1 pr-3">{p.strategy}</td>
                      <td className="py-1 pr-3">{p.timeframe}</td>
                      <td className={`py-1 pr-3 ${p.return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{p.return_pct}%</td>
                      <td className="py-1 pr-3 text-rose-300">{p.max_drawdown_pct}%</td>
                      <td className="py-1 pr-3">{p.win_rate}%</td>
                      <td className="py-1 pr-3">{p.sharpe}</td>
                      <td className="py-1 pr-3">{p.total_trades}</td>
                      <td className="py-1 pr-3">
                        {p.oos_held_up == null ? '—' : p.oos_held_up ? <Badge tone="pos">held</Badge> : <Badge tone="neg">failed</Badge>}
                      </td>
                      <td className="py-1 pr-3">
                        <button
                          onClick={() => remove(p)}
                          disabled={removing === p.active_id}
                          className="px-2 py-0.5 rounded text-xs bg-rose-500/20 text-rose-300 border border-rose-500/40 disabled:opacity-50"
                        >
                          {removing === p.active_id ? '…' : 'Remove'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <button
            onClick={() => setShowAll((v) => !v)}
            className="mt-3 text-xs text-slate-400 hover:text-slate-200"
          >
            {showAll ? 'Hide' : 'Show'} all {res.candidates.length} tested combos
          </button>
          {showAll && (
            <div className="overflow-x-auto mt-2 max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="text-slate-500 text-left sticky top-0 bg-[#11151f]">
                  <tr>
                    <th className="py-1 pr-3">Coin</th><th className="py-1 pr-3">Strategy</th>
                    <th className="py-1 pr-3">TF</th><th className="py-1 pr-3">Score</th>
                    <th className="py-1 pr-3">Return</th><th className="py-1 pr-3">Max DD</th>
                    <th className="py-1 pr-3">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {res.candidates.map((c, i) => (
                    <tr key={i} className={`border-t border-slate-800 ${c.recommended ? 'text-slate-200' : 'text-slate-500'}`}>
                      <td className="py-1 pr-3">{c.symbol.replace('USDT', '')}</td>
                      <td className="py-1 pr-3">{c.strategy}</td>
                      <td className="py-1 pr-3">{c.timeframe}</td>
                      <td className="py-1 pr-3">{c.score ?? '—'}</td>
                      <td className="py-1 pr-3">{c.return_pct}%</td>
                      <td className="py-1 pr-3">{c.max_drawdown_pct}%</td>
                      <td className="py-1 pr-3">{c.recommended ? '✓ selected-eligible' : c.excluded_reasons.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Card>
  )
}
