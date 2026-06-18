import type { ReactNode } from 'react'

type PageHeaderProps = {
  title: string
  subtitle?: string
  badge?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ title, subtitle, badge, actions }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4 pb-5">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold text-slate-900">{title}</h1>
          {badge}
        </div>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}
