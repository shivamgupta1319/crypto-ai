import { useCallback, useEffect, useState } from 'react'
import { api, type ActiveStrategy, type CurrentSetup, type LiveSignal, type ScanStatus } from '../api/client'
import { Badge, Card, PageTitle } from '../components/ui'
import { useSignalFeed } from '../hooks/useSignalFeed'

function StatusDot({ status }: { status: string }) {
  const tone = status === 'live' ? 'pos' : status === 'offline' ? 'neg' : 'warn'
  return <Badge tone={tone}>{status === 'live' ? '● live' : status === 'offline' ? '● offline' : '● connecting'}</Badge>
}

function stateTone(s: string): 'pos' | 'neg' | 'neutral' {
  return s === 'LONG' ? 'pos' : s === 'SHORT' ? 'neg' : 'neutral'
}

export default function Scanner() {
  const { signals, status, setSignals } = useSignalFeed()
  const [active, setActive] = useState<ActiveStrategy[]>([])
  const [setups, setSetups] = useState<CurrentSetup[]>([])
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null)
  const [scope, setScope] = useState<'active' | 'all'>('active')
  const [scanning, setScanning] = useState(false)
  const [loadingSetups, setLoadingSetups] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const refreshActive = useCallback(() => {
    api.getActive().then(setActive).catch(() => setActive([]))
    api.getScanStatus().then(setScanStatus).catch(() => {})
  }, [])

  const refreshSetups = useCallback((s: 'active' | 'all') => {
    setLoadingSetups(true)
    api
      .getCurrentSetups(s)
      .then((r) => setSetups(r.setups))
      .catch(() => setSetups([]))
      .finally(() => setLoadingSetups(false))
  }, [])

  useEffect(() => {
    refreshActive()
    const id = setInterval(refreshActive, 20000)
    return () => clearInterval(id)
  }, [refreshActive])

  useEffect(() => {
    refreshSetups(scope)
  }, [scope, refreshSetups])

  async function removeActive(id: number) {
    await api.deleteActive(id).catch(() => {})
    refreshActive()
    if (scope === 'active') refreshSetups('active')
  }

  async function scanNow() {
    setScanning(true)
    setNote(null)
    try {
      const res = await api.scanNow()
      if (res.count > 0) {
        setSignals((prev) => {
          const ids = new Set(prev.map((s) => s.id))
          return [...res.new_signals.filter((s) => !ids.has(s.id)), ...prev].slice(0, 200)
        })
      }
      setNote(`scan complete · ${res.count} new signal(s) · ${res.opened} opened · ${res.closed} closed`)
      refreshSetups(scope)
      refreshActive()
    } catch (e) {
      setNote(String((e as Error).message))
    } finally {
      setScanning(false)
    }
  }

  const lastScan = scanStatus?.last_scan_at ? new Date(scanStatus.last_scan_at).toLocaleTimeString() : '—'

  return (
    <div>
      <div className="flex items-center justify-between">
        <PageTitle title="Live Signals / Scanner" subtitle="Live state of your strategies + triggered signals" />
        <div className="flex items-center gap-3">
          <StatusDot status={status} />
          <button
            onClick={scanNow}
            disabled={scanning}
            className="px-3 py-1.5 rounded-md bg-emerald-500 text-slate-900 text-sm font-medium disabled:opacity-40"
          >
            {scanning ? 'Scanning…' : 'Scan now'}
          </button>
        </div>
      </div>

      {/* Scanner status bar */}
      <Card className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-1 py-2.5 text-sm">
        <span className="text-slate-400">
          Monitoring <span className="text-slate-100 font-medium">{scanStatus?.monitored ?? 0}</span> promoted strategies
        </span>
        <span className="text-slate-400">
          Auto-scan every <span className="text-slate-100">{scanStatus?.interval_s ?? 60}s</span>
        </span>
        <span className="text-slate-400">Last scan: <span className="text-slate-100">{lastScan}</span></span>
        <Badge tone="neutral">Long &amp; Short</Badge>
        <Badge tone={scanStatus?.alerts_enabled ? 'pos' : 'neutral'}>
          alerts {scanStatus?.alerts_enabled ? 'on' : 'off'}
        </Badge>
        {scanStatus?.price_stream && <Badge tone="pos">live prices</Badge>}
        {note && <span className="text-xs text-slate-500 ml-auto">{note}</span>}
      </Card>

      {/* Active (promoted) strategies with remove */}
      <h2 className="text-sm text-slate-400 mb-2">Promoted strategies ({active.length})</h2>
      {active.length === 0 ? (
        <Card className="border-dashed mb-6">
          <p className="text-slate-400 text-sm">
            None promoted yet. Go to <span className="text-emerald-300">Backtesting</span>, run a strategy
            (try a <span className="text-emerald-300">5m</span> or <span className="text-emerald-300">15m</span>
            {' '}timeframe for frequent signals), and click <span className="text-blue-300">Promote to live</span>.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
          {active.map((a) => (
            <Card key={a.id} className="flex items-center justify-between py-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{a.symbol}</span>
                  <Badge>{a.timeframe}</Badge>
                </div>
                <div className="text-sm text-slate-400 mt-1">{a.strategy}</div>
              </div>
              <button
                onClick={() => removeActive(a.id)}
                className="px-2.5 py-1 rounded-md text-xs bg-rose-500/20 text-rose-300 border border-rose-500/40"
              >
                Remove
              </button>
            </Card>
          ))}
        </div>
      )}

      {/* Current setups: always populated live state */}
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm text-slate-400">Current Setups (live state)</h2>
        <div className="flex gap-1">
          {(['active', 'all'] as const).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`px-2.5 py-1 rounded text-xs ${
                scope === s ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {s === 'active' ? 'Promoted' : 'All strategies'}
            </button>
          ))}
        </div>
      </div>
      {loadingSetups ? (
        <p className="text-slate-500 text-sm mb-6">Evaluating strategies on live data…</p>
      ) : setups.length === 0 ? (
        <Card className="border-dashed mb-6">
          <p className="text-slate-400 text-sm">
            {scope === 'active'
              ? 'No promoted strategies to evaluate. Switch to "All strategies" to preview the whole library.'
              : 'No setups available right now.'}
          </p>
        </Card>
      ) : (
        <Card className="mb-6 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-slate-500 text-left">
              <tr>
                <th className="py-1 pr-4">Symbol</th>
                <th className="py-1 pr-4">TF</th>
                <th className="py-1 pr-4">Strategy</th>
                <th className="py-1 pr-4">State</th>
                <th className="py-1 pr-4">Price</th>
                <th className="py-1 pr-4">Entry</th>
                <th className="py-1 pr-4">Stop</th>
                <th className="py-1 pr-4">Target</th>
                <th className="py-1 pr-4">R:R</th>
                <th className="py-1 pr-4">Conf</th>
                <th className="py-1 pr-4">Bars</th>
              </tr>
            </thead>
            <tbody>
              {setups.map((s, i) => (
                <tr key={i} className="border-t border-slate-800">
                  <td className="py-1 pr-4 font-medium">{s.symbol}</td>
                  <td className="py-1 pr-4 text-slate-500">{s.timeframe}</td>
                  <td className="py-1 pr-4 text-slate-400">{s.strategy}</td>
                  <td className="py-1 pr-4">
                    <Badge tone={stateTone(s.state)}>{s.state}</Badge>
                    {s.fresh && <span className="ml-1 text-xs text-amber-300">new</span>}
                  </td>
                  <td className="py-1 pr-4">{s.price}</td>
                  <td className="py-1 pr-4">{s.entry ?? '—'}</td>
                  <td className="py-1 pr-4 text-rose-300">{s.stop ?? '—'}</td>
                  <td className="py-1 pr-4 text-emerald-300">{s.target ?? '—'}</td>
                  <td className="py-1 pr-4">{s.rr ?? '—'}</td>
                  <td className="py-1 pr-4">{(s.confidence * 100).toFixed(0)}%</td>
                  <td className="py-1 pr-4 text-slate-500">{s.bars_in_state}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Triggered signal feed (transition events) */}
      <h2 className="text-sm text-slate-400 mb-2">Triggered signals ({signals.length})</h2>
      {signals.length === 0 ? (
        <p className="text-slate-500 text-sm">No triggers yet — these fire when a strategy flips direction.</p>
      ) : (
        <div className="space-y-2">
          {signals.map((s) => (
            <SignalRow key={s.id} s={s} />
          ))}
        </div>
      )}
    </div>
  )
}

function SignalRow({ s }: { s: LiveSignal }) {
  return (
    <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 py-3">
      <div className="flex items-center gap-2 min-w-[140px]">
        <Badge tone={s.direction === 'LONG' ? 'pos' : 'neg'}>{s.direction}</Badge>
        <span className="font-semibold">{s.symbol}</span>
        <span className="text-xs text-slate-500">{s.timeframe}</span>
      </div>
      <div className="text-sm text-slate-400">{s.strategy}</div>
      <div className="flex gap-5 text-sm">
        <span><span className="text-slate-500">Entry </span>{s.entry}</span>
        <span className="text-rose-300"><span className="text-slate-500">Stop </span>{s.stop}</span>
        <span className="text-emerald-300"><span className="text-slate-500">Target </span>{s.target}</span>
        <span><span className="text-slate-500">Conf </span>{(s.confidence * 100).toFixed(0)}%</span>
      </div>
      <div className="text-xs text-slate-600 ml-auto">{new Date(s.created_at).toLocaleString()}</div>
    </Card>
  )
}
