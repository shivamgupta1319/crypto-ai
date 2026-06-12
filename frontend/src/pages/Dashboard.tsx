import { useEffect, useState } from 'react'
import {
  api,
  type AccountSummary,
  type LiveSignal,
  type MarketOutlook,
} from '../api/client'
import { Badge, Card, PageTitle, Stat } from '../components/ui'
import { AiInsightCard } from '../components/AiPanel'
import { MarketIntel } from '../components/MarketIntel'

function regimeTone(regime?: string): 'pos' | 'neg' | 'warn' | 'neutral' {
  if (regime === 'uptrend') return 'pos'
  if (regime === 'downtrend') return 'neg'
  if (regime === 'ranging') return 'warn'
  return 'neutral'
}

export default function Dashboard() {
  const [data, setData] = useState<MarketOutlook | null>(null)
  const [account, setAccount] = useState<AccountSummary | null>(null)
  const [signals, setSignals] = useState<LiveSignal[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = () => {
      api.getOutlook().then(setData).catch((e) => setError(String(e.message))).finally(() => setLoading(false))
      api.getSummary().then(setAccount).catch(() => {})
      api.getSignals(6).then(setSignals).catch(() => {})
    }
    load()
    const id = setInterval(load, 15000) // live auto-refresh
    return () => clearInterval(id)
  }, [])

  return (
    <div>
      <PageTitle title="Market Outlook" subtitle="Live snapshot of BTC, ETH, SOL perpetual futures + your paper account" />

      {loading && <p className="text-slate-400">Loading live market data…</p>}
      {error && <p className="text-rose-400">Error: {error}</p>}

      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
            <Card>
              <Stat
                label="Fear & Greed"
                value={data.fear_greed.value != null ? `${data.fear_greed.value}` : '—'}
              />
              <div className="text-xs text-slate-500 mt-1">{data.fear_greed.classification}</div>
            </Card>
            <Card>
              <Stat
                label="Breadth"
                value={
                  <Badge tone={data.market_breadth === 'bullish' ? 'pos' : data.market_breadth === 'bearish' ? 'neg' : 'warn'}>
                    {data.market_breadth}
                  </Badge>
                }
              />
            </Card>
            <Card>
              <Stat
                label="Paper Equity"
                value={account ? account.equity.toLocaleString() : '—'}
              />
            </Card>
            <Card>
              <Stat
                label="Realized P&L"
                value={account ? account.realized_pnl.toLocaleString() : '—'}
                tone={account ? (account.realized_pnl >= 0 ? 'pos' : 'neg') : undefined}
              />
            </Card>
            <Card>
              <Stat label="Open Positions" value={account ? account.open_positions : '—'} />
            </Card>
            <Card>
              <Stat label="Win Rate" value={account ? `${account.win_rate}%` : '—'} />
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            {data.coins.map((c) => (
              <Card key={c.symbol}>
                <div className="flex items-center justify-between mb-3">
                  <span className="font-semibold text-lg">{c.symbol}</span>
                  {c.available && <Badge tone={regimeTone(c.regime)}>{c.regime}</Badge>}
                </div>
                {!c.available ? (
                  <p className="text-slate-500 text-sm">No data yet — fetching candles…</p>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-end justify-between">
                      <span className="text-2xl font-semibold">${c.price?.toLocaleString()}</span>
                      <span className={(c.change_24h_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                        {(c.change_24h_pct ?? 0) >= 0 ? '+' : ''}
                        {c.change_24h_pct}%
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-sm">
                      <Stat label="RSI(14)" value={c.rsi} />
                      <Stat label="ADX(14)" value={c.adx} />
                      <Stat
                        label="MACD"
                        value={<Badge tone={c.macd_state === 'bullish' ? 'pos' : 'neg'}>{c.macd_state}</Badge>}
                      />
                      <Stat label="Boll %B" value={c.bb_pct} />
                      <Stat label="ATR%" value={c.atr_pct} />
                      <Stat
                        label="Vol x avg"
                        value={c.vol_ratio}
                        tone={(c.vol_ratio ?? 1) >= 1.3 ? 'pos' : undefined}
                      />
                    </div>
                  </div>
                )}
              </Card>
            ))}
          </div>

          <MarketIntel />

          <div className="mb-6">
            <AiInsightCard
              title="AI Market Commentary"
              buttonLabel="Generate"
              run={() => api.aiCommentary()}
            />
          </div>

          <Card>
            <div className="font-medium mb-3">Latest Signals</div>
            {signals.length === 0 ? (
              <p className="text-slate-500 text-sm">
                No signals yet. Promote a strategy on the Backtesting page to start the scanner.
              </p>
            ) : (
              <div className="space-y-1">
                {signals.map((s) => (
                  <div key={s.id} className="flex items-center gap-3 text-sm py-1">
                    <Badge tone={s.direction === 'LONG' ? 'pos' : 'neg'}>{s.direction}</Badge>
                    <span className="font-medium w-20">{s.symbol}</span>
                    <span className="text-slate-400 w-32">{s.strategy}</span>
                    <span className="text-slate-500">@ {s.entry}</span>
                    <span className="text-xs text-slate-600 ml-auto">{new Date(s.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}
