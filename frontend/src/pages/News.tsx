import { useEffect, useState } from 'react'
import { api, type NewsItem } from '../api/client'
import { Badge, Card, PageTitle } from '../components/ui'

const COINS = ['ALL', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT']

function sentimentTone(s: string): 'pos' | 'neg' | 'neutral' {
  return s === 'positive' ? 'pos' : s === 'negative' ? 'neg' : 'neutral'
}

export default function News() {
  const [coin, setCoin] = useState('ALL')
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    api
      .getNews(coin === 'ALL' ? undefined : coin)
      .then(setItems)
      .catch((e) => setError(String(e.message)))
      .finally(() => setLoading(false))
  }, [coin])

  return (
    <div>
      <PageTitle title="Crypto News" subtitle="Aggregated free RSS feeds with a quick sentiment read" />

      <div className="flex gap-2 mb-4">
        {COINS.map((c) => (
          <button
            key={c}
            onClick={() => setCoin(c)}
            className={`px-3 py-1.5 rounded-md text-sm ${
              coin === c ? 'bg-emerald-500/15 text-emerald-300' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {c === 'ALL' ? 'All' : c.replace('USDT', '')}
          </button>
        ))}
      </div>

      {loading && <p className="text-slate-400">Loading headlines…</p>}
      {error && <p className="text-rose-400">Error: {error}</p>}
      {!loading && items.length === 0 && <p className="text-slate-500 text-sm">No headlines found.</p>}

      <div className="space-y-2">
        {items.map((it, idx) => (
          <Card key={idx} className="py-3">
            <div className="flex items-start gap-3">
              <div className="flex-1">
                <a
                  href={it.link}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium hover:text-emerald-300"
                >
                  {it.title}
                </a>
                {it.summary && (
                  <p className="text-sm text-slate-500 mt-1 line-clamp-2">
                    {it.summary.replace(/<[^>]*>/g, '')}
                  </p>
                )}
                <div className="flex items-center gap-2 mt-2 text-xs text-slate-500">
                  <span>{it.source}</span>
                  {it.published_ts && <span>· {new Date(it.published_ts).toLocaleString()}</span>}
                  {it.coins.map((c) => (
                    <Badge key={c}>{c.replace('USDT', '')}</Badge>
                  ))}
                </div>
              </div>
              <Badge tone={sentimentTone(it.sentiment)}>{it.sentiment}</Badge>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
