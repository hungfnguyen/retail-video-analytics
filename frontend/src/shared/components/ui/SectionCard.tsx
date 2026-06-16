import type { ReactNode } from 'react'

type SectionCardProps = {
  title: string
  subtitle?: string
  badge?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}

export function SectionCard({ title, subtitle, badge, actions, children, className = '' }: SectionCardProps) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
            {badge}
          </div>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}
