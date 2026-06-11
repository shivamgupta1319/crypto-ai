import { useEffect, useState } from 'react'
import { api, type SettingField, type SettingsView } from '../api/client'
import { Badge, Card, PageTitle } from '../components/ui'

type Values = Record<string, number | boolean | string[]>

const ALL_TF = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']

export default function Settings() {
  const [view, setView] = useState<SettingsView | null>(null)
  const [draft, setDraft] = useState<Values>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  function load() {
    api.getSettings().then((v) => {
      setView(v)
      setDraft({ ...v.values })
    })
  }
  useEffect(load, [])

  function set(key: string, value: number | boolean | string[]) {
    setDraft((d) => ({ ...d, [key]: value }))
    setSaved(false)
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const v = await api.updateSettings(draft)
      setView(v)
      setDraft({ ...v.values })
      setSaved(true)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function reset() {
    if (!window.confirm('Reset all settings to their defaults from config.py?')) return
    const v = await api.resetSettings()
    setView(v)
    setDraft({ ...v.values })
    setSaved(true)
  }

  if (!view) return <p className="text-slate-400">Loading settings…</p>

  return (
    <div>
      <div className="flex items-center justify-between">
        <PageTitle title="Settings" subtitle="Tune risk, leverage, and the traded universe — saved to the database" />
        <div className="flex gap-2">
          <button onClick={reset} className="px-3 py-1.5 rounded-md text-sm border border-slate-700 text-slate-300 hover:border-slate-500">
            Reset to defaults
          </button>
          <button onClick={save} disabled={saving} className="px-4 py-1.5 rounded-md text-sm bg-emerald-500 text-slate-900 font-medium disabled:opacity-40">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {error && <p className="text-rose-400 text-sm mb-4">{error}</p>}
      {saved && <Badge tone="pos">Saved ✓</Badge>}

      <Card className="mt-4 space-y-4">
        {view.fields.map((f) => (
          <Row key={f.key} field={f} value={draft[f.key]} onChange={(v) => set(f.key, v)} />
        ))}
      </Card>
      <p className="text-xs text-slate-500 mt-3">
        Risk/leverage changes apply immediately to new trades. Universe changes apply to the
        next dashboard/scan cycle. Scan-interval changes apply on the next backend restart.
      </p>
    </div>
  )
}

function Row({
  field,
  value,
  onChange,
}: {
  field: SettingField
  value: number | boolean | string[]
  onChange: (v: number | boolean | string[]) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-4 border-b border-slate-800 pb-3 last:border-0">
      <div className="w-56">
        <div className="text-sm font-medium">{field.label}</div>
        {field.note && <div className="text-xs text-slate-500">{field.note}</div>}
        {(field.min != null || field.max != null) && (
          <div className="text-xs text-slate-600">range {field.min} – {field.max}</div>
        )}
      </div>
      <div className="flex-1">
        {field.kind === 'bool' ? (
          <button
            onClick={() => onChange(!(value as boolean))}
            className={`px-3 py-1 rounded-md text-sm border ${
              value ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-slate-700 text-slate-400'
            }`}
          >
            {value ? 'Enabled' : 'Disabled'}
          </button>
        ) : field.kind === 'symbols' ? (
          <input
            value={(value as string[]).join(', ')}
            onChange={(e) => onChange(e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
            className="w-full px-3 py-1.5 rounded-md bg-slate-900 border border-slate-700 text-sm"
            placeholder="BTCUSDT, ETHUSDT, SOLUSDT"
          />
        ) : field.kind === 'timeframes' ? (
          <div className="flex flex-wrap gap-2">
            {ALL_TF.map((tf) => {
              const on = (value as string[]).includes(tf)
              return (
                <button
                  key={tf}
                  onClick={() => {
                    const cur = value as string[]
                    onChange(on ? cur.filter((t) => t !== tf) : [...cur, tf])
                  }}
                  className={`px-2 py-1 rounded text-xs border ${
                    on ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-slate-700 text-slate-400'
                  }`}
                >
                  {tf}
                </button>
              )
            })}
          </div>
        ) : (
          <input
            type="number"
            value={value as number}
            min={field.min ?? undefined}
            max={field.max ?? undefined}
            step={field.kind === 'int' ? 1 : 0.1}
            onChange={(e) => onChange(Number(e.target.value))}
            className="w-32 px-3 py-1.5 rounded-md bg-slate-900 border border-slate-700 text-sm"
          />
        )}
      </div>
    </div>
  )
}
