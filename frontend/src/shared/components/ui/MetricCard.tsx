import type { ComponentType, ReactNode } from 'react'

export type MetricTone = 'blue' | 'green' | 'amber' | 'red' | 'violet' | 'slate'

export type MetricCardProps = {
  label: string
  value: string | number
  unit?: string
  meta?: string
  icon?: ComponentType<{ size?: number; className?: string }>
  tone?: MetricTone
  children?: ReactNode
}

const toneClasses: Record<MetricTone, { bg: string; text: string; icon: string }> = {
  blue:   { bg: 'bg-blue-50',   text: 'text-blue-700',   icon: 'text-blue-500' },
  green:  { bg: 'bg-emerald-50', text: 'text-emerald-700', icon: 'text-emerald-500' },
  amber:  { bg: 'bg-amber-50',  text: 'text-amber-700',  icon: 'text-amber-500' },
  red:    { bg: 'bg-red-50',    text: 'text-red-700',    icon: 'text-red-500' },
  violet: { bg: 'bg-violet-50', text: 'text-violet-700', icon: 'text-violet-500' },
  slate:  { bg: 'bg-slate-100', text: 'text-slate-700',  icon: 'text-slate-500' },
}

export function MetricCard({ label, value, unit, meta, icon: Icon, tone = 'slate', children }: MetricCardProps) {
  const cls = toneClasses[tone]
  return (
    <div className={`rounded-xl border border-slate-200 ${cls.bg} p-4`}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</span>
        {Icon && <Icon size={16} className={cls.icon} />}
      </div>
      <div className="mt-1.5 flex items-baseline gap-1">
        <span className={`text-2xl font-bold ${cls.text}`}>{value}</span>
        {unit && <span className="text-sm font-medium text-slate-500">{unit}</span>}
      </div>
      {meta && <p className="mt-1 text-xs text-slate-500">{meta}</p>}
      {children}
    </div>
  )
}
