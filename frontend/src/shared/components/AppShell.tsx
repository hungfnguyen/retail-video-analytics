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
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">R</div>
          <div>
            <strong>RVA</strong>
            <span>Retail Video Analytics</span>
          </div>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <button
                className={item.active ? 'nav-item active' : 'nav-item'}
                key={item.label}
                type="button"
              >
                <Icon size={18} />
                {item.label}
              </button>
            )
          })}
        </nav>
        <div className="sidebar-user">
          <div className="avatar">A</div>
          <div>
            <strong>admin</strong>
            <span>Administrator</span>
          </div>
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  )
}
