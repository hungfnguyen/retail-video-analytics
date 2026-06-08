import { Activity, AlertTriangle, Clock, Users } from 'lucide-react'
import type { Alert, LiveStats, ZoneCount } from '../types'

type LiveMetricCardsProps = {
  alerts: Alert[]
  stats: LiveStats
  zoneCounts: ZoneCount[]
}

function formatUpdatedAt(value: string) {
  if (!value) {
    return 'No live frame'
  }

  const updatedAt = new Date(value)
  if (Number.isNaN(updatedAt.getTime())) {
    return 'Updated from realtime state'
  }

  return `Updated ${updatedAt.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })}`
}

function formatDuration(totalSeconds = 0) {
  const safeSeconds = Math.max(0, Math.round(totalSeconds))
  const minutes = Math.floor(safeSeconds / 60)
  const seconds = safeSeconds % 60

  if (minutes > 0) {
    return `${minutes}m ${seconds.toString().padStart(2, '0')}s`
  }

  return `${seconds}s`
}

function zoneOccupancyCount(zoneCounts: ZoneCount[]) {
  const uniqueGlobalIds = new Set(
    zoneCounts.flatMap((zone) => zone.global_track_ids ?? []),
  )
  if (uniqueGlobalIds.size > 0) {
    return uniqueGlobalIds.size
  }

  return zoneCounts.reduce((sum, zone) => sum + Math.max(0, zone.count), 0)
}

export function LiveMetricCards({ alerts, stats, zoneCounts }: LiveMetricCardsProps) {
  const queueZones = zoneCounts.filter((zone) => zone.zone_type === 'queue')
  const queueLength = queueZones.reduce((sum, zone) => sum + Math.max(0, zone.count), 0)
  const currentCount = Math.max(stats.current_count, zoneOccupancyCount(zoneCounts))
  const longestWaitSeconds = Math.max(
    0,
    ...queueZones.map((zone) => Math.floor(Math.max(0, zone.max_wait_ms ?? 0) / 1000)),
  )
  const activeAlertCount = alerts.filter((alert) => alert.status === 'new').length

  const metrics = [
    {
      label: 'Current count',
      value: currentCount,
      meta: formatUpdatedAt(stats.updated_at),
      icon: Users,
    },
    {
      label: 'Queue length',
      value: queueLength,
      meta: 'People in queue zones',
      icon: Activity,
    },
    {
      label: 'Longest wait',
      value: formatDuration(longestWaitSeconds),
      meta: 'Max queue wait',
      icon: Clock,
    },
    {
      label: 'Active alerts',
      value: activeAlertCount,
      meta: activeAlertCount > 0 ? 'Needs review' : 'No active alerts',
      icon: AlertTriangle,
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
