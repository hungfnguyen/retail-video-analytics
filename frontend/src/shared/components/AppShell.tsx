import type { ReactNode } from 'react'
import { BarChart3, Camera, Search, Settings } from 'lucide-react'

type AppShellProps = {
  children: ReactNode
}

const navItems = [
  { label: 'Live', icon: Camera, active: true },
  { label: 'Analytics', icon: BarChart3, active: false },
  { label: 'Investigate', icon: Search, active: false },
  { label: 'System', icon: Settings, active: false },
]

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="grid min-h-screen grid-cols-[248px_1fr] bg-slate-100 text-slate-950">

      {/* Sidebar */}
      <aside className="flex flex-col border-r border-slate-800 bg-slate-950 px-3.5 py-6 text-white shadow-2xl">

        {/* Brand */}
        <div className="flex items-center gap-3 px-2 pb-7">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-white font-extrabold text-slate-950 shadow-sm">R</div>
          <div>
            <strong className="block text-[28px] font-extrabold leading-none tracking-wide text-white">RVA</strong>
            <span className="block text-[13px] font-medium text-slate-300">Retail Video Analytics</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="grid gap-2">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <button
                className={
                  item.active
                    ? 'flex items-center gap-3 rounded-lg bg-blue-600 px-3.5 py-3 text-left font-semibold text-white shadow-[0_12px_26px_rgba(37,99,235,0.35)]'
                    : 'flex items-center gap-3 rounded-lg bg-transparent px-3.5 py-3 text-left font-semibold text-slate-300 transition hover:bg-slate-800 hover:text-white'
                }
                key={item.label}
                type="button"
              >
                <Icon size={18} />
                {item.label}
              </button>
            )
          })}
        </nav>

        {/* Current user */}
        <div className="mt-auto flex items-center gap-2.5 border-t border-white/15 px-2 pt-4">
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
