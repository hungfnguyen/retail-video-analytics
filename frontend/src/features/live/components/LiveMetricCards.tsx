import { Activity, Clock, Footprints, Users } from 'lucide-react'
import type { LiveStats } from '../types'

type LiveMetricCardsProps = {
  stats: LiveStats
}

export function LiveMetricCards({ stats }: LiveMetricCardsProps) {
  const metrics = [
    {
      label: 'Current count',
      value: stats.current_count,
      meta: `+${stats.count_change_percent}% vs previous 5 minutes`,
      icon: Users,
    },
    {
      label: 'Active tracks',
      value: stats.active_tracks,
      meta: `+${stats.tracks_change_percent}% vs previous 5 minutes`,
      icon: Footprints,
    },
    {
      label: 'FPS',
      value: stats.fps.toFixed(1),
      meta: 'Stable',
      icon: Activity,
    },
    {
      label: 'Latency',
      value: `${stats.latency_ms} ms`,
      meta: 'Stable',
      icon: Clock,
    },
  ]

  return (
    <section className="grid grid-cols-4 gap-3" aria-label="Live metrics">
      {metrics.map((metric) => {
        const Icon = metric.icon
        return (
          <article
            className="min-h-32 rounded-lg border border-slate-200 bg-white p-4.5 shadow-[0_18px_45px_rgba(15,23,42,0.08)]"
            key={metric.label}
          >
            <div className="flex items-center justify-between text-slate-500">
              <span>{metric.label}</span>
              <Icon size={18} />
            </div>

            <strong className="my-4 block text-[34px] leading-none text-blue-600">{metric.value}</strong>

            <small className="text-slate-500">{metric.meta}</small>
          </article>
        )
      })}
    </section>
  )
}
