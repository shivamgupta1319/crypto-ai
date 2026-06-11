import { useEffect, useState } from 'react'
import { api, type AiResponse, type AiStatus } from '../api/client'
import { AiStatusBadge } from './AiPanel'
import { Card } from './ui'

const SUGGESTIONS = [
  'Which strategy is performing best?',
  'What is my biggest risk right now?',
  'Summarize my recent losing trades.',
]

/** Natural-language Q&A grounded in the paper account (advisory only). */
export function AskAiCard() {
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AiResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getAiStatus().then(setStatus).catch(() => setStatus({ enabled: false, provider: null, model: null }))
  }, [])

  async function ask(q: string) {
    const query = q.trim()
    if (!query) return
    setLoading(true)
    setError(null)
    try {
      setAnswer(await api.aiAsk(query))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const disabled = status != null && !status.enabled

  return (
    <Card>
      <div className="flex items-center gap-2 mb-3">
        <h3 className="font-semibold">Ask AI about your account</h3>
        <AiStatusBadge status={status} />
      </div>

      {disabled ? (
        <p className="text-sm text-slate-400">
          AI is not configured. Add an API key to <code className="text-slate-300">backend/.env</code>{' '}
          (Gemini or OpenRouter — both free, no card).
        </p>
      ) : (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              ask(question)
            }}
            className="flex gap-2"
          >
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. Which strategy is losing money?"
              className="flex-1 px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm focus:border-indigo-500 outline-none"
            />
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-sm font-medium"
            >
              {loading ? 'Thinking…' : 'Ask'}
            </button>
          </form>

          <div className="flex flex-wrap gap-2 mt-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setQuestion(s)
                  ask(s)
                }}
                disabled={loading}
                className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-400 hover:border-slate-500 disabled:opacity-40"
              >
                {s}
              </button>
            ))}
          </div>

          {error && <p className="text-sm text-rose-400 mt-3">{error}</p>}
          {answer?.text && (
            <div className="mt-3 text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">
              {answer.text}
            </div>
          )}
          <p className="text-xs text-slate-600 mt-2">Advisory only — the AI never places trades.</p>
        </>
      )}
    </Card>
  )
}
