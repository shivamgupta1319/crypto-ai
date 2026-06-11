import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/scanner', label: 'Live Signals' },
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/backtest', label: 'Backtesting' },
  { to: '/news', label: 'News' },
  { to: '/agent', label: 'Agent' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-slate-800 bg-[#0e1320]">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
          <div className="font-bold text-lg tracking-tight">
            crypto<span className="text-emerald-400">ai</span>
            <span className="ml-2 text-xs font-normal text-slate-500">paper trading</span>
          </div>
          <nav className="flex gap-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm transition-colors ${
                    isActive
                      ? 'bg-emerald-500/15 text-emerald-300'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
