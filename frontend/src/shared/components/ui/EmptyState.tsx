import type { ComponentType } from 'react'
import { InboxIcon } from 'lucide-react'

type EmptyStateTone = 'neutral' | 'warning' | 'error'

type EmptyStateProps = {
  title: string
  description?: string
  icon?: ComponentType<{ size?: number; className?: string }>
  tone?: EmptyStateTone
}

const toneClasses: Record<EmptyStateTone, { border: string; text: string; icon: string }> = {
  neutral: { border: 'border-slate-200',  text: 'text-slate-500',  icon: 'text-slate-300' },
  warning: { border: 'border-amber-200',  text: 'text-amber-700',  icon: 'text-amber-300' },
  error:   { border: 'border-red-200',    text: 'text-red-700',    icon: 'text-red-300' },
}

export function EmptyState({ title, description, icon: Icon = InboxIcon, tone = 'neutral' }: EmptyStateProps) {
  const cls = toneClasses[tone]
  return (
    <div className={`grid min-h-32 place-items-center rounded-lg border border-dashed ${cls.border} py-8`}>
      <div className="flex flex-col items-center gap-2 text-center">
        <Icon size={28} className={cls.icon} />
        <p className={`text-sm font-medium ${cls.text}`}>{title}</p>
        {description && <p className="text-xs text-slate-400 max-w-xs">{description}</p>}
      </div>
    </div>
  )
}
