import { useEffect, useState } from 'react'
import { api, type AiResponse, type AiStatus } from '../api/client'
import { Badge, Card } from './ui'

/** Renders multi-paragraph AI text with basic spacing. */
function AiText({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">
      {text.split(/\n{2,}/).map((para, i) => (
        <p key={i}>{para}</p>
      ))}
    </div>
  )
}

export function AiStatusBadge({ status }: { status: AiStatus | null }) {
  if (!status) return null
  if (!status.enabled) return <Badge tone="neutral">AI off</Badge>
  return (
    <Badge tone="pos">
      AI · {status.provider}
      {status.model ? ` (${status.model.split('/').pop()})` : ''}
    </Badge>
  )
}

/**
 * Generic AI insight card: a title, a generate button, and the rendered result.
 * `run` is the async call that returns an AiResponse (commentary / explain / ask).
 */
export function AiInsightCard({
  title,
  buttonLabel = 'Generate',
  run,
  auto = false,
}: {
  title: string
  buttonLabel?: string
  run: () => Promise<AiResponse>
  auto?: boolean
}) {
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [result, setResult] = useState<AiResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getAiStatus().then(setStatus).catch(() => setStatus({ enabled: false, provider: null, model: null }))
  }, [])

  async function generate() {
    setLoading(true)
    setError(null)
    try {
      const res = await run()
      setResult(res)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // Auto-run once AI is known to be enabled.
  useEffect(() => {
    if (auto && status?.enabled && !result && !loading) generate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, status?.enabled])

  const disabled = status != null && !status.enabled

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold">{title}</h3>
          <AiStatusBadge status={status} />
        </div>
        <button
          onClick={generate}
          disabled={loading || disabled}
          className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium"
        >
          {loading ? 'Thinking…' : result ? 'Regenerate' : buttonLabel}
        </button>
      </div>

      {disabled && (
        <p className="text-sm text-slate-400">
          AI is not configured. Add <code className="text-slate-300">CRYPTOAI_GEMINI_API_KEY</code>{' '}
          or <code className="text-slate-300">CRYPTOAI_OPENROUTER_API_KEY</code> to{' '}
          <code className="text-slate-300">backend/.env</code> (both free, no card).
        </p>
      )}
      {error && <p className="text-sm text-rose-400">{error}</p>}
      {!disabled && !result && !loading && !error && (
        <p className="text-sm text-slate-500">Advisory only — never places trades. Click {buttonLabel.toLowerCase()}.</p>
      )}
      {result?.text && <AiText text={result.text} />}
      {result?.cached && <p className="text-xs text-slate-600 mt-2">cached</p>}
    </Card>
  )
}
