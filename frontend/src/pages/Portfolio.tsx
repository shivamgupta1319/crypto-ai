import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type AccountSummary,
  type ClosedTrade,
  type EquityPoint,
  type OpenPosition,
  type PortfolioHistoryPoint,
  type RiskView,
  type StrategyAttribution,
} from '../api/client'
import { Badge, Card, PageTitle, Stat } from '../components/ui'
import EquityChart from '../components/EquityChart'
import PerformanceChart, { type ChartPoint } from '../components/PerformanceChart'
import { AskAiCard } from '../components/AskAiCard'
import { useWsEvents } from '../hooks/useWsEvents'

// Drawdown % from peak, computed from the persisted equity snapshots.
function computeDrawdown(hist: PortfolioHistoryPoint[]): ChartPoint[] {
  let peak = -Infinity
  return hist.map((h) => {
    peak = Math.max(peak, h.equity)
    const dd = peak > 0 ? ((h.equity - peak) / peak) * 100 : 0
    return { time: h.time, value: Number(dd.toFixed(2)) }
  })
}

const POLL_MS = 5000

type TabKey = 'overview' | 'charts' | 'history' | 'risk'

function pnlTone(n: number): 'pos' | 'neg' | undefined {
  return n > 0 ? 'pos' : n < 0 ? 'neg' : undefined
}

export default function Portfolio() {
  const [summary, setSummary] = useState<AccountSummary | null>(null)
  const [positions, setPositions] = useState<OpenPosition[]>([])
  const [trades, setTrades] = useState<ClosedTrade[]>([])
  const [equity, setEquity] = useState<EquityPoint[]>([])
  const [history, setHistory] = useState<PortfolioHistoryPoint[]>([])
  const [attribution, setAttribution] = useState<StrategyAttribution[]>([])
  const [risk, setRisk] = useState<RiskView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabKey>('overview')

  const refresh = useCallback(() => {
    Promise.all([
      api.getSummary(), api.getPositions(), api.getTrades(), api.getPortfolioEquity(),
      api.getAttribution(), api.getRisk(), api.getPortfolioHistory(),
    ])
      .then(([s, p, t, e, a, r, h]) => {
        setSummary(s)
        setPositions(p)
        setTrades(t)
        setEquity(e)
        setAttribution(a)
        setRisk(r)
        setHistory(h)
        setError(null)
      })
      .catch((err) => setError(String(err.message)))
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, POLL_MS)
    return () => clearInterval(id)
  }, [refresh])

  // Refresh immediately when a trade opens/closes (don't wait for the poll).
  useWsEvents((msg) => {
    if (msg.type === 'trade_opened' || msg.type === 'trade_closed') refresh()
  })

  const [closing, setClosing] = useState<number | null>(null)
  async function closePosition(id: number) {
    setClosing(id)
    try {
      await api.closePosition(id)
      refresh()
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setClosing(null)
    }
  }

  async function resetAccount() {
    if (!window.confirm('Reset the paper account? This deletes all paper trades (open + closed). Active strategies are kept.')) return
    try {
      await api.resetAccount()
      refresh()
    } catch (e) {
      setError(String((e as Error).message))
    }
  }

  const cur = summary?.display_currency ?? ''

  const TABS: { key: TabKey; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'charts', label: 'Charts' },
    { key: 'history', label: `History (${trades.length})` },
    { key: 'risk', label: 'Risk & Strategies' },
  ]

  return (
    <div>
      <div className="flex items-center justify-between">
        <PageTitle title="Portfolio / Paper Trading" subtitle="Live paper account · auto-updates every 5s" />
        <div className="flex items-center gap-2">
          {summary?.kill_switch && <Badge tone="neg">⛔ Daily loss limit hit</Badge>}
          <a
            href="/api/portfolio/export"
            className="px-3 py-1.5 rounded-md text-sm border border-slate-700 text-slate-300 hover:border-slate-500"
          >
            Export CSV
          </a>
          <button
            onClick={resetAccount}
            className="px-3 py-1.5 rounded-md text-sm bg-rose-500/20 text-rose-300 border border-rose-500/40"
          >
            Reset account
          </button>
        </div>
      </div>

      {error && <p className="text-rose-400 text-sm mb-4">{error}</p>}

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-slate-800 mb-6 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm whitespace-nowrap -mb-px border-b-2 ${
              tab === t.key
                ? 'border-emerald-400 text-slate-100 font-medium'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ---- Overview: KPI stats + open positions ---- */}
      {tab === 'overview' && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
            <Card><Stat label="Equity" value={summary ? `${summary.equity.toLocaleString()} ${cur}` : '—'} /></Card>
            <Card><Stat label="Balance" value={summary ? `${summary.balance.toLocaleString()} ${cur}` : '—'} /></Card>
            <Card>
              <Stat
                label="Unrealized P&L"
                value={summary ? summary.unrealized_pnl.toLocaleString() : '—'}
                tone={summary ? pnlTone(summary.unrealized_pnl) : undefined}
              />
            </Card>
            <Card>
              <Stat
                label="Realized P&L"
                value={summary ? summary.realized_pnl.toLocaleString() : '—'}
                tone={summary ? pnlTone(summary.realized_pnl) : undefined}
              />
            </Card>
            <Card>
              <Stat
                label="Return"
                value={summary ? `${summary.return_pct}%` : '—'}
                tone={summary ? pnlTone(summary.return_pct) : undefined}
              />
            </Card>
            <Card><Stat label="Win Rate" value={summary ? `${summary.win_rate}%` : '—'} /></Card>
          </div>

          <h2 className="text-sm text-slate-400 mb-2">Open Positions ({positions.length})</h2>
          {positions.length === 0 ? (
            <Card className="border-dashed mb-6">
              <p className="text-slate-400 text-sm">
                No open positions. The paper-trader auto-opens trades from signals on your{' '}
                <span className="text-emerald-300">promoted</span> strategies (risk-checked).
              </p>
            </Card>
          ) : (
            <div className="space-y-2 mb-6">
              {positions.map((p) => (
                <Card key={p.id} className="flex flex-wrap items-center gap-x-6 gap-y-2 py-3">
                  <div className="flex items-center gap-2 min-w-[150px]">
                    <Badge tone={p.direction === 'LONG' ? 'pos' : 'neg'}>{p.direction}</Badge>
                    <span className="font-semibold">{p.symbol}</span>
                    <span className="text-xs text-slate-500">{p.leverage}x</span>
                  </div>
                  <span className="text-sm text-slate-400">{p.strategy}</span>
                  <div className="flex gap-5 text-sm">
                    <span><span className="text-slate-500">Entry </span>{p.entry_price}</span>
                    <span><span className="text-slate-500">Now </span>{p.current_price}</span>
                    <span className="text-rose-300"><span className="text-slate-500">Stop </span>{p.stop}</span>
                    <span className="text-emerald-300"><span className="text-slate-500">Tgt </span>{p.target}</span>
                  </div>
                  <div className={`ml-auto font-semibold ${p.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {p.unrealized_pnl >= 0 ? '+' : ''}
                    {p.unrealized_pnl}
                  </div>
                  <button
                    onClick={() => closePosition(p.id)}
                    disabled={closing === p.id}
                    className="px-3 py-1 rounded-md text-xs bg-rose-500/20 text-rose-300 border border-rose-500/40 disabled:opacity-50"
                  >
                    {closing === p.id ? 'Closing…' : 'Close'}
                  </button>
                </Card>
              ))}
            </div>
          )}

          <AskAiCard />
        </>
      )}

      {/* ---- Charts ---- */}
      {tab === 'charts' && (
        <>
          {equity.length > 1 ? (
            <Card className="mb-6">
              <div className="font-medium mb-3">Equity Curve (realized)</div>
              <EquityChart series={[{ label: 'equity', color: '#34d399', data: equity }]} />
            </Card>
          ) : (
            <Card className="border-dashed mb-6">
              <p className="text-slate-400 text-sm">No closed trades yet — the realized equity curve appears after the first trade closes.</p>
            </Card>
          )}

          {/* Performance analytics from persisted per-cycle snapshots (incl. unrealized) */}
          {history.length > 1 && (() => {
            const drawdown = computeDrawdown(history)
            const maxDd = Math.min(0, ...drawdown.map((d) => d.value))
            const peakEquity = Math.max(...history.map((h) => h.equity))
            const eqValues = history.map((h) => h.equity)
            // No variation yet (idle account) → a flat line reads as "broken", so show
            // a collecting-state note until equity actually moves.
            const flat = Math.max(...eqValues) === Math.min(...eqValues)
            const collecting = (
              <div className="h-[200px] flex flex-col items-center justify-center text-center px-4">
                <p className="text-slate-400 text-sm">Collecting snapshots ({history.length} so far)</p>
                <p className="text-slate-500 text-xs mt-1">
                  Recorded each scan cycle (~60s). This fills in once open positions move the equity —
                  promote a strategy (Backtest → Auto-Select) to drive activity.
                </p>
              </div>
            )
            return (
              <div className="grid lg:grid-cols-2 gap-4 mb-6">
                <Card>
                  <div className="font-medium mb-3">Equity over time (incl. unrealized)</div>
                  {flat ? collecting : (
                    <PerformanceChart
                      series={[
                        { label: 'equity', color: '#34d399', type: 'line', data: history.map((h) => ({ time: h.time, value: h.equity })) },
                        { label: 'realized', color: '#60a5fa', type: 'line', data: history.map((h) => ({ time: h.time, value: h.realized_balance })) },
                      ]}
                    />
                  )}
                  <p className="text-xs text-slate-500 mt-2">
                    <span className="text-emerald-400">equity</span> tracks open-position swings;{' '}
                    <span className="text-sky-400">realized</span> is balance from closed trades only.
                  </p>
                </Card>
                <Card>
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-medium">Drawdown from peak</span>
                    <div className="flex gap-4">
                      <Stat label="Peak equity" value={`${peakEquity.toLocaleString()} ${cur}`} />
                      <Stat label="Max drawdown" value={`${maxDd.toFixed(2)}%`} tone={maxDd < 0 ? 'neg' : undefined} />
                    </div>
                  </div>
                  {flat ? collecting : (
                    <PerformanceChart series={[{ label: 'drawdown', color: '#f43f5e', type: 'area', data: drawdown }]} />
                  )}
                </Card>
              </div>
            )
          })()}
        </>
      )}

      {/* ---- History ---- */}
      {tab === 'history' && (
        <>
          <h2 className="text-sm text-slate-400 mb-2">Trade History ({trades.length})</h2>
          {trades.length === 0 ? (
            <p className="text-slate-500 text-sm">No closed trades yet.</p>
          ) : (
            <Card>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-slate-500 text-left">
                    <tr>
                      <th className="py-1 pr-4">Symbol</th>
                      <th className="py-1 pr-4">Dir</th>
                      <th className="py-1 pr-4">Strategy</th>
                      <th className="py-1 pr-4">Entry</th>
                      <th className="py-1 pr-4">Exit</th>
                      <th className="py-1 pr-4">P&L</th>
                      <th className="py-1 pr-4">Closed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t) => (
                      <tr key={t.id} className="border-t border-slate-800">
                        <td className="py-1 pr-4 font-medium">{t.symbol}</td>
                        <td className="py-1 pr-4">
                          <Badge tone={t.direction === 'LONG' ? 'pos' : 'neg'}>{t.direction}</Badge>
                        </td>
                        <td className="py-1 pr-4 text-slate-400">{t.strategy}</td>
                        <td className="py-1 pr-4">{t.entry_price}</td>
                        <td className="py-1 pr-4">{t.exit_price}</td>
                        <td className={`py-1 pr-4 ${t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{t.pnl}</td>
                        <td className="py-1 pr-4 text-slate-600">
                          {t.closed_at ? new Date(t.closed_at).toLocaleString() : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}

      {/* ---- Risk & Strategies ---- */}
      {tab === 'risk' && (
        <>
          {risk && risk.positions.length > 0 ? (
            <Card className="mb-6">
              <div className="flex items-center gap-3 mb-3">
                <span className="font-medium">Risk</span>
                {risk.correlation_warning && (
                  <Badge tone="warn">⚠ positions all same direction — correlated risk</Badge>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
                <Stat label="Gross exposure" value={`${risk.gross_exposure.toLocaleString()} (${risk.gross_exposure_pct}%)`} />
                <Stat label="Net exposure" value={risk.net_exposure.toLocaleString()} />
                <Stat label="Margin used" value={`${risk.margin_used.toLocaleString()} (${risk.margin_used_pct}%)`} />
                <Stat label="Concentration" value={Object.entries(risk.concentration_pct).map(([s, v]) => `${s.replace('USDT', '')} ${v}%`).join(' · ') || '—'} />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-slate-500 text-left">
                    <tr><th className="py-1 pr-4">Symbol</th><th className="py-1 pr-4">Dir</th><th className="py-1 pr-4">Lev</th><th className="py-1 pr-4">Notional</th><th className="py-1 pr-4">Margin</th><th className="py-1 pr-4">Est. liquidation</th></tr>
                  </thead>
                  <tbody>
                    {risk.positions.map((p) => (
                      <tr key={p.id} className="border-t border-slate-800">
                        <td className="py-1 pr-4 font-medium">{p.symbol}</td>
                        <td className="py-1 pr-4"><Badge tone={p.direction === 'LONG' ? 'pos' : 'neg'}>{p.direction}</Badge></td>
                        <td className="py-1 pr-4">{p.leverage}x</td>
                        <td className="py-1 pr-4">{p.notional.toLocaleString()}</td>
                        <td className="py-1 pr-4">{p.margin.toLocaleString()}</td>
                        <td className="py-1 pr-4 text-amber-300">{p.liquidation_price}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-slate-500 mt-2">Liquidation price is an estimate (isolated margin + maintenance margin; ignores fees).</p>
            </Card>
          ) : (
            <Card className="border-dashed mb-6">
              <p className="text-slate-400 text-sm">No open positions — risk exposure appears here when positions are open.</p>
            </Card>
          )}

          {/* Strategy P&L attribution */}
          {attribution.length > 0 && (
            <Card className="mb-6">
              <div className="font-medium mb-3">Strategy P&L (which strategy earns)</div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-slate-500 text-left">
                    <tr><th className="py-1 pr-4">Strategy</th><th className="py-1 pr-4">Trades</th><th className="py-1 pr-4">Net P&L</th><th className="py-1 pr-4">Win%</th><th className="py-1 pr-4">Avg P&L</th><th className="py-1 pr-4">Profit factor</th></tr>
                  </thead>
                  <tbody>
                    {attribution.map((a) => (
                      <tr key={a.strategy} className="border-t border-slate-800">
                        <td className="py-1 pr-4">{a.strategy}</td>
                        <td className="py-1 pr-4">{a.trades}</td>
                        <td className={`py-1 pr-4 ${a.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{a.net_pnl}</td>
                        <td className="py-1 pr-4">{a.win_rate}%</td>
                        <td className="py-1 pr-4">{a.avg_pnl}</td>
                        <td className="py-1 pr-4">{a.profit_factor ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
