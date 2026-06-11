import type { ReactNode } from 'react'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-slate-800 bg-[#11151f] p-4 ${className}`}>
      {children}
    </div>
  )
}

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-5">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {subtitle && <p className="text-sm text-slate-400 mt-1">{subtitle}</p>}
    </div>
  )
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: 'pos' | 'neg' }) {
  const color = tone === 'pos' ? 'text-emerald-400' : tone === 'neg' ? 'text-rose-400' : 'text-slate-100'
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`text-lg font-semibold ${color}`}>{value}</div>
    </div>
  )
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'pos' | 'neg' | 'warn' | 'neutral' }) {
  const tones: Record<string, string> = {
    pos: 'bg-emerald-500/15 text-emerald-300',
    neg: 'bg-rose-500/15 text-rose-300',
    warn: 'bg-amber-500/15 text-amber-300',
    neutral: 'bg-slate-700/40 text-slate-300',
  }
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${tones[tone]}`}>{children}</span>
}

export function ComingSoon({ phase, blurb }: { phase: string; blurb: string }) {
  return (
    <Card className="border-dashed">
      <div className="text-amber-300 text-sm font-medium mb-1">{phase}</div>
      <p className="text-slate-400 text-sm">{blurb}</p>
    </Card>
  )
}
