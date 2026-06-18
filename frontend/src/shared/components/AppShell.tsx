import type { ReactNode } from 'react'
import { BarChart3, Camera, Map, Settings } from 'lucide-react'

export type AppPage = 'live' | 'analytics' | 'heatmap' | 'system'

type AppShellProps = {
  activePage: AppPage
  children: ReactNode
  onPageChange: (page: AppPage) => void
}

const navItems = [
  { id: 'live' as const, label: 'Live Monitor', icon: Camera },
  { id: 'analytics' as const, label: 'Analytics', icon: BarChart3 },
  { id: 'heatmap' as const, label: 'Heatmap', icon: Map },
  { id: 'system' as const, label: 'System', icon: Settings },
]

export function AppShell({ activePage, children, onPageChange }: AppShellProps) {
  return (
    <div className="grid min-h-screen grid-cols-[258px_1fr] bg-slate-100 text-slate-950">

      {/* Sidebar */}
      <aside className="flex flex-col border-r border-slate-800 bg-[radial-gradient(circle_at_top,_rgba(67,56,202,0.22),_transparent_32%),linear-gradient(180deg,_#071129_0%,_#060b19_100%)] px-4 py-6 text-white shadow-2xl">

        {/* Brand */}
        <div className="flex items-center gap-3 px-2 pb-8">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-white font-extrabold text-slate-950 shadow-sm">R</div>
          <div>
            <strong className="block text-[28px] font-extrabold leading-none tracking-wide text-white">RVA</strong>
            <span className="block text-[12px] font-medium text-slate-300">Retail Video Analytics</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="grid gap-2.5">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = item.id === activePage

            return (
              <button
                className={
                  isActive
                    ? 'flex items-center gap-3 rounded-xl bg-[linear-gradient(90deg,_#4f46e5_0%,_#7c3aed_100%)] px-3.5 py-3 text-left font-semibold text-white shadow-[0_14px_28px_rgba(79,70,229,0.38)]'
                    : 'flex items-center gap-3 rounded-xl bg-transparent px-3.5 py-3 text-left font-semibold text-slate-300 transition hover:bg-white/5 hover:text-white'
                }
                key={item.label}
                onClick={() => onPageChange(item.id)}
                type="button"
              >
                <Icon size={18} />
                {item.label}
              </button>
            )
          })}
        </nav>

        <div className="mt-auto rounded-xl border border-white/10 bg-white/5 p-3 text-white/90">
          <p className="text-[11px] uppercase tracking-wide text-slate-400">Store</p>
          <div className="mt-2 flex items-center justify-between rounded-lg bg-white/6 px-3 py-2">
            <span className="text-sm font-medium">Store A</span>
            <span className="text-slate-400">⌄</span>
          </div>
        </div>

        {/* Current user */}
        <div className="mt-4 flex items-center gap-2.5 border-t border-white/10 px-2 pt-4">
          <div className="grid h-9 w-9 place-items-center rounded-full bg-blue-100 font-bold text-slate-950">A</div>
          <div>
            <strong className="block font-semibold text-white">admin</strong>
            <span className="block text-[13px] font-medium text-slate-300">Administrator</span>
          </div>
        </div>

      </aside>

      <main className="bg-slate-50 p-5.5 text-slate-950">{children}</main>
      
    </div>
  )
}
