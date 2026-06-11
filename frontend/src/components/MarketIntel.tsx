import { useEffect, useState } from 'react'
import { api, type CorrelationView, type DerivativesView } from '../api/client'
import { Badge, Card, Stat } from './ui'

function fundingTone(pct: number | null): 'pos' | 'neg' | 'warn' | 'neutral' {
  if (pct == null) return 'neutral'
  if (pct > 0.03) return 'neg' // crowded longs paying — caution
  if (pct < -0.03) return 'pos'
  return 'neutral'
}

function corrColor(v: number): string {
  // 1 = strongly correlated (amber/red), 0 = independent (slate), negative = green.
  if (v >= 0.8) return 'bg-rose-500/30'
  if (v >= 0.5) return 'bg-amber-500/25'
  if (v <= -0.2) return 'bg-emerald-500/25'
  return 'bg-slate-700/30'
}

function compactUsd(n: number | null): string {
  if (n == null) return '—'
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`
  return `$${n.toLocaleString()}`
}

export function MarketIntel() {
  const [deriv, setDeriv] = useState<DerivativesView | null>(null)
  const [corr, setCorr] = useState<CorrelationView | null>(null)

  useEffect(() => {
    const load = () => {
      api.getDerivatives().then(setDeriv).catch(() => {})
      api.getCorrelation().then(setCorr).catch(() => {})
    }
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
  }, [])

  const g = deriv?.global
  const anyDeriv = deriv?.coins?.some((c) => c.available)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
      {/* Global stats */}
      <Card>
        <div className="font-medium mb-3">Global</div>
        {g ? (
          <div className="grid grid-cols-2 gap-3">
            <Stat label="BTC Dominance" value={`${g.btc_dominance_pct}%`} />
            <Stat label="ETH Dominance" value={`${g.eth_dominance_pct}%`} />
            <Stat label="Total Mcap" value={compactUsd(g.total_market_cap_usd)} />
            <Stat
              label="Mcap 24h"
              value={`${g.market_cap_change_24h_pct}%`}
              tone={g.market_cap_change_24h_pct >= 0 ? 'pos' : 'neg'}
            />
          </div>
        ) : (
          <p className="text-slate-500 text-sm">Global stats unavailable.</p>
        )}
      </Card>

      {/* Derivatives per coin */}
      <Card>
        <div className="font-medium mb-3">Perp Derivatives</div>
        {anyDeriv ? (
          <div className="space-y-2 text-sm">
            <div className="grid grid-cols-4 gap-2 text-xs text-slate-500">
              <span>Coin</span><span>Funding</span><span>L/S</span><span>OI</span>
            </div>
            {deriv!.coins.map((c) => (
              <div key={c.symbol} className="grid grid-cols-4 gap-2 items-center">
                <span className="font-medium">{c.symbol.replace('USDT', '')}</span>
                {c.funding_rate_pct != null ? (
                  <Badge tone={fundingTone(c.funding_rate_pct)}>{c.funding_rate_pct}%</Badge>
                ) : (
                  <span className="text-slate-600">—</span>
                )}
                <span className={c.long_short_ratio != null && c.long_short_ratio > 1 ? 'text-emerald-400' : 'text-rose-400'}>
                  {c.long_short_ratio ?? '—'}
                </span>
                <span className="text-slate-400">
                  {c.open_interest != null ? c.open_interest.toLocaleString() : '—'}
                </span>
              </div>
            ))}
            <p className="text-xs text-slate-600 mt-1">
              Funding is per-8h; high positive = crowded longs (fade risk).
            </p>
          </div>
        ) : (
          <p className="text-slate-500 text-sm">Derivatives data unavailable in this environment.</p>
        )}
      </Card>

      {/* Correlation matrix */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <span className="font-medium">Correlation (1h returns)</span>
          {corr?.avg_correlation != null && (
            <Badge tone={corr.avg_correlation >= 0.7 ? 'warn' : 'neutral'}>
              avg {corr.avg_correlation}
            </Badge>
          )}
        </div>
        {corr?.available ? (
          <table className="text-sm w-full">
            <thead>
              <tr className="text-slate-500 text-xs">
                <th></th>
                {corr.symbols.map((s) => (
                  <th key={s} className="px-1 font-normal">{s.replace('USDT', '')}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {corr.matrix.map((row, i) => (
                <tr key={corr.symbols[i]}>
                  <td className="text-slate-500 text-xs pr-2">{corr.symbols[i].replace('USDT', '')}</td>
                  {row.map((v, j) => (
                    <td key={j} className={`text-center py-1 ${corrColor(v)}`}>{v}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-slate-500 text-sm">Not enough data for correlation.</p>
        )}
        {corr?.avg_correlation != null && corr.avg_correlation >= 0.7 && (
          <p className="text-xs text-amber-300 mt-2">
            ⚠ Coins move together — holding all three is concentrated, not diversified.
          </p>
        )}
      </Card>
    </div>
  )
}
