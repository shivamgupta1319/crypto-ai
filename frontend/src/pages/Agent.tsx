import { useCallback, useEffect, useState } from 'react'
import { api, type AgentOverview, type AgentProposal, type RegimeView } from '../api/client'
import { Badge, Card, PageTitle, Stat } from '../components/ui'

function regimeTone(r: string): 'pos' | 'neg' | 'warn' | 'neutral' {
  if (r === 'trending_up') return 'pos'
  if (r === 'trending_down') return 'neg'
  if (r === 'high_vol') return 'warn'
  return 'neutral'
}

export default function Agent() {
  const [ov, setOv] = useState<AgentOverview | null>(null)
  const [regime, setRegime] = useState<RegimeView | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    api.getAgentOverview().then(setOv).catch((e) => setError(String(e.message)))
    api.getAgentRegime().then(setRegime).catch(() => {})
  }, [])
  useEffect(refresh, [refresh])

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label)
    setError(null)
    try {
      await fn()
      refresh()
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy(null)
    }
  }

  if (!ov) return <p className="text-slate-400">Loading agent…</p>

  return (
    <div>
      <div className="flex items-center justify-between">
        <PageTitle
          title="Adaptive Agent"
          subtitle="Learns from results & market regime to propose improvements — paper-only, you approve every change"
        />
        <button
          onClick={() => act('review', api.agentReview)}
          disabled={busy === 'review'}
          className="px-4 py-1.5 rounded-md text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 font-medium"
        >
          {busy === 'review' ? 'Reviewing…' : 'Run review cycle'}
        </button>
      </div>

      {error && <p className="text-rose-400 text-sm mb-4">{error}</p>}

      {/* Regime + status strip */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card>
          <div className="font-medium mb-2">Market regime</div>
          <div className="space-y-1">
            {regime?.regimes.map((r) => (
              <div key={r.symbol} className="flex items-center justify-between text-sm">
                <span>{r.symbol.replace('USDT', '')}</span>
                <Badge tone={regimeTone(r.regime)}>{r.label}</Badge>
              </div>
            )) ?? <span className="text-slate-500 text-sm">—</span>}
          </div>
        </Card>
        <Card>
          <div className="font-medium mb-2">Meta-label filter</div>
          <Stat label="Status" value={ov.meta_label_enabled ? 'ON' : 'OFF'} tone={ov.meta_label_enabled ? 'pos' : undefined} />
          <div className="text-xs text-slate-500 mt-1">P(win) threshold {ov.meta_label_threshold} · edit in Settings</div>
          <div className="text-xs text-slate-500 mt-2">{ov.model.models.length} model(s) trained</div>
        </Card>
        <Card>
          <div className="font-medium mb-2">Training data</div>
          <Stat label="Labeled samples" value={ov.dataset.total} />
          <button
            onClick={() => act('train', () => api.agentTrain(null))}
            disabled={busy === 'train' || ov.dataset.total < (ov.model.min_samples ?? 100)}
            className="mt-2 px-3 py-1 rounded text-xs bg-slate-700 hover:bg-slate-600 disabled:opacity-40"
          >
            {busy === 'train' ? 'Training…' : 'Train global model'}
          </button>
          <div className="text-xs text-slate-500 mt-1">Build samples from a backtest first (≥ {ov.model.min_samples ?? 100}).</div>
        </Card>
      </div>

      {ov.narrative && (
        <Card className="mb-6 border-indigo-500/30 bg-indigo-500/5">
          <div className="font-medium mb-2">Agent assessment {ov.ai_enabled ? '' : '(AI off)'}</div>
          <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">{ov.narrative}</p>
        </Card>
      )}

      {/* Pending proposals */}
      <h2 className="text-sm text-slate-400 mb-2">Pending proposals ({ov.pending_proposals.length})</h2>
      {ov.pending_proposals.length === 0 ? (
        <Card className="border-dashed mb-6">
          <p className="text-slate-400 text-sm">
            No proposals. Run a review cycle once you have enough paper-trading history — the agent
            proposes disabling losers, scaling winners, and tuning the meta-label filter.
          </p>
        </Card>
      ) : (
        <div className="space-y-2 mb-6">
          {ov.pending_proposals.map((p) => (
            <ProposalRow key={p.id} p={p} busy={busy}
              onApprove={() => act(`a${p.id}`, () => api.agentApprove(p.id))}
              onReject={() => act(`r${p.id}`, () => api.agentReject(p.id))} />
          ))}
        </div>
      )}

      {/* Strategy performance / allocation */}
      <h2 className="text-sm text-slate-400 mb-2">Strategy performance</h2>
      <Card className="mb-6">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-slate-500 text-left">
              <tr>
                <th className="py-1 pr-4">Strategy</th><th className="py-1 pr-4">Trades</th>
                <th className="py-1 pr-4">Net P&L</th><th className="py-1 pr-4">Win%</th>
                <th className="py-1 pr-4">Size x</th><th className="py-1 pr-4">State</th>
              </tr>
            </thead>
            <tbody>
              {ov.allocation.strategies.map((s) => (
                <tr key={s.strategy} className="border-t border-slate-800">
                  <td className="py-1 pr-4">{s.strategy}</td>
                  <td className="py-1 pr-4">{s.trades}</td>
                  <td className={`py-1 pr-4 ${s.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{s.net_pnl}</td>
                  <td className="py-1 pr-4">{s.win_rate}%</td>
                  <td className="py-1 pr-4">{ov.levers.size_multipliers[s.strategy] ?? 1}x</td>
                  <td className="py-1 pr-4">
                    {s.active ? <Badge tone={s.enabled ? 'pos' : 'neg'}>{s.enabled ? 'enabled' : 'disabled'}</Badge> : <span className="text-slate-600">—</span>}
                  </td>
                </tr>
              ))}
              {ov.allocation.strategies.length === 0 && (
                <tr><td colSpan={6} className="py-2 text-slate-500">No closed paper trades yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Recent decisions (revertable) */}
      {ov.recent_proposals.some((p) => p.status !== 'pending') && (
        <>
          <h2 className="text-sm text-slate-400 mb-2">Decision history</h2>
          <Card>
            <div className="space-y-1">
              {ov.recent_proposals.filter((p) => p.status !== 'pending').map((p) => (
                <div key={p.id} className="flex items-center gap-3 text-sm py-1">
                  <Badge tone={p.status === 'approved' ? 'pos' : p.status === 'reverted' ? 'warn' : 'neutral'}>{p.status}</Badge>
                  <span className="flex-1">{p.title}</span>
                  {p.status === 'approved' && (
                    <button
                      onClick={() => act(`rev${p.id}`, () => api.agentRevert(p.id))}
                      disabled={busy === `rev${p.id}`}
                      className="px-2 py-0.5 rounded text-xs border border-slate-700 text-slate-300 hover:border-slate-500"
                    >
                      Revert
                    </button>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}

function ProposalRow({
  p, busy, onApprove, onReject,
}: {
  p: AgentProposal
  busy: string | null
  onApprove: () => void
  onReject: () => void
}) {
  return (
    <Card className="flex flex-wrap items-center gap-4 py-3">
      <div className="flex-1 min-w-[300px]">
        <div className="flex items-center gap-2">
          <span className="font-medium">{p.title}</span>
          <Badge tone="neutral">{p.kind}</Badge>
          <span className="text-xs text-slate-500">conf {Math.round(p.confidence * 100)}%</span>
        </div>
        <p className="text-sm text-slate-400 mt-1">{p.rationale}</p>
      </div>
      <div className="flex gap-2">
        <button
          onClick={onApprove}
          disabled={busy === `a${p.id}`}
          className="px-3 py-1 rounded-md text-sm bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 disabled:opacity-40"
        >
          Approve
        </button>
        <button
          onClick={onReject}
          disabled={busy === `r${p.id}`}
          className="px-3 py-1 rounded-md text-sm bg-rose-500/20 text-rose-300 border border-rose-500/40 disabled:opacity-40"
        >
          Reject
        </button>
      </div>
    </Card>
  )
}
