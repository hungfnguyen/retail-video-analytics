import type { ComponentType, ReactNode } from 'react'

export type MetricTone = 'blue' | 'green' | 'emerald' | 'amber' | 'red' | 'violet' | 'slate'

type MetricTrendTone = 'positive' | 'negative' | 'neutral' | 'alert'

export type MetricCardProps = {
  label: string
  value: string | number
  unit?: string
  meta?: string
  trend?: {
    value: string
    tone?: MetricTrendTone
  }
  icon?: ComponentType<{ size?: number; className?: string }>
  tone?: MetricTone
  children?: ReactNode
}

const toneClasses: Record<MetricTone, { bg: string; border: string; iconBg: string; icon: string; value: string }> = {
  blue:    { bg: 'bg-white', border: 'border-blue-100',   iconBg: 'bg-blue-50',    icon: 'text-blue-500',    value: 'text-slate-900' },
  green:   { bg: 'bg-white', border: 'border-emerald-100', iconBg: 'bg-emerald-50', icon: 'text-emerald-500', value: 'text-slate-900' },
  emerald: { bg: 'bg-white', border: 'border-emerald-100', iconBg: 'bg-emerald-50', icon: 'text-emerald-500', value: 'text-slate-900' },
  amber:   { bg: 'bg-white', border: 'border-amber-100',  iconBg: 'bg-amber-50',   icon: 'text-amber-500',   value: 'text-slate-900' },
  red:     { bg: 'bg-white', border: 'border-red-100',    iconBg: 'bg-red-50',     icon: 'text-red-500',     value: 'text-red-600' },
  violet:  { bg: 'bg-white', border: 'border-violet-100', iconBg: 'bg-violet-50',  icon: 'text-violet-500',  value: 'text-slate-900' },
  slate:   { bg: 'bg-white', border: 'border-slate-200',  iconBg: 'bg-slate-100',  icon: 'text-slate-500',   value: 'text-slate-900' },
}

const trendToneClasses: Record<MetricTrendTone, string> = {
  positive: 'text-emerald-600',
  negative: 'text-red-500',
  neutral: 'text-slate-500',
  alert: 'text-amber-600',
}

export function MetricCard({ label, value, unit, meta, trend, icon: Icon, tone = 'slate', children }: MetricCardProps) {
  const cls = toneClasses[tone]
  return (
    <div className={`rounded-2xl border ${cls.border} ${cls.bg} px-4 py-3.5 shadow-sm`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="block text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span className={`text-[2rem] font-bold leading-none ${cls.value}`}>{value}</span>
            {unit && <span className="text-sm font-medium text-slate-500">{unit}</span>}
          </div>
        </div>
        {Icon && (
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${cls.iconBg}`}>
            <Icon size={18} className={cls.icon} />
          </div>
        )}
      </div>
      {(meta || trend) && (
        <div className="mt-2 min-h-8">
          {trend && (
            <p className={`text-xs font-medium ${trendToneClasses[trend.tone ?? 'neutral']}`}>
              {trend.value}
            </p>
          )}
          {meta && <p className="mt-0.5 text-xs text-slate-500">{meta}</p>}
        </div>
      )}
      {children}
    </div>
  )
}
