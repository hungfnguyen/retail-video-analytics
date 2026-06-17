export type BadgeStatus = 'low' | 'medium' | 'high' | 'ok' | 'warning' | 'critical' | 'normal' | 'live'

type StatusBadgeProps = {
  status: BadgeStatus
  label?: string
}

const statusClasses: Record<BadgeStatus, string> = {
  live:     'bg-green-500 text-white',
  ok:       'bg-emerald-100 text-emerald-700',
  normal:   'bg-emerald-100 text-emerald-700',
  low:      'bg-slate-100 text-slate-600',
  medium:   'bg-amber-100 text-amber-700',
  warning:  'bg-amber-100 text-amber-700',
  high:     'bg-red-100 text-red-700',
  critical: 'bg-red-100 text-red-700',
}

const defaultLabels: Record<BadgeStatus, string> = {
  live:     'LIVE',
  ok:       'OK',
  normal:   'Normal',
  low:      'Low',
  medium:   'Medium',
  warning:  'Warning',
  high:     'High',
  critical: 'Critical',
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${statusClasses[status]}`}>
      {label ?? defaultLabels[status]}
    </span>
  )
}
