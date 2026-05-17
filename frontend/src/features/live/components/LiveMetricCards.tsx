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
    <section className="metric-grid" aria-label="Live metrics">
      {metrics.map((metric) => {
        const Icon = metric.icon
        return (
          <article className="metric-card" key={metric.label}>
            <div className="metric-card-header">
              <span>{metric.label}</span>
              <Icon size={18} />
            </div>
            <strong>{metric.value}</strong>
            <small>{metric.meta}</small>
          </article>
        )
      })}
    </section>
  )
}
