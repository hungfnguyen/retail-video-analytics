import { Bell, CalendarDays, Clock3, Footprints, TimerReset } from 'lucide-react'
import type { MetricCardProps } from '../../../shared/components/ui/MetricCard'
import { formatDuration, formatNumber } from '../../../shared/utils/format'
import type {
  AlertHistoryData,
  AnalyticsDashboardData,
  QueueAnalyticsData,
  QueueZoneStat,
  TopZonePoint,
} from '../types'
import type { BadgeStatus } from '../../../shared/components/ui/StatusBadge'

export type QueueStatusRow = QueueZoneStat & { status: BadgeStatus }

export type AlertTrendRow = { date: string; high: number; medium: number; low: number }

export function buildOverviewKpis(
  data: AnalyticsDashboardData | null,
  _queueData: QueueAnalyticsData | null,
): MetricCardProps[] {
  const totalVisitors = data?.total_visitors ?? 0
  const peakDay = data?.peak_day
  const peakHour = data?.peak_hour
  const avgDwellSec = data?.avg_dwell_sec ?? 0

  return [
    {
      label: 'Total Visitors',
      value: formatNumber(totalVisitors),
      tone: 'blue',
      icon: Footprints,
      meta: data?.range_label ?? 'Selected period',
      trend: totalVisitors > 0 ? { value: `↑ Active across ${data?.daily_summary.length ?? 0} day(s)`, tone: 'positive' } : undefined,
    },
    {
      label: 'Peak Day',
      value: peakDay ? new Date(peakDay.date).toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' }) : '—',
      tone: 'violet',
      icon: CalendarDays,
      meta: peakDay ? `${formatNumber(peakDay.visitors)} visitors` : 'No daily peak yet',
    },
    {
      label: 'Peak Hour',
      value: peakHour?.hour ?? '—',
      tone: 'amber',
      icon: Clock3,
      meta: peakHour ? `${formatNumber(peakHour.visitors)} visitors` : 'No hourly peak yet',
    },
    {
      label: 'Avg Dwell Time',
      value: avgDwellSec > 0 ? formatDuration(avgDwellSec) : '—',
      tone: 'green',
      icon: TimerReset,
      meta: avgDwellSec > 0 ? 'Historical engagement time' : 'No dwell data yet',
    },
  ]
}

export function buildAlertKpis(alertData: AlertHistoryData | null): MetricCardProps[] {
  const records = alertData?.records ?? []
  const total = records.length
  const high = records.filter((r) => r.severity === 'high').length

  const typeCounts = records.reduce<Record<string, number>>((acc, r) => {
    acc[r.alert_type] = (acc[r.alert_type] ?? 0) + 1
    return acc
  }, {})
  const mostCommonType = Object.entries(typeCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—'

  const zoneCounts = records.reduce<Record<string, number>>((acc, r) => {
    if (r.zone) acc[r.zone] = (acc[r.zone] ?? 0) + 1
    return acc
  }, {})
  const mostAffectedZone = Object.entries(zoneCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—'

  return [
    { label: 'Total Alerts', value: total, tone: total > 0 ? 'amber' : 'green', icon: Bell, meta: 'Selected period' },
    { label: 'High Severity', value: high, tone: high > 0 ? 'red' : 'green', icon: Bell, meta: high > 0 ? 'Needs review' : 'No critical alerts' },
    { label: 'Most Common Type', value: mostCommonType.replace(/_/g, ' '), tone: 'violet', icon: Clock3, meta: `${typeCounts[mostCommonType] ?? 0} occurrences` },
    { label: 'Most Affected Zone', value: mostAffectedZone.replace(/_/g, ' '), tone: 'slate', icon: Footprints, meta: `${zoneCounts[mostAffectedZone] ?? 0} alerts` },
  ]
}

export function buildAlertTrendByDay(alertData: AlertHistoryData | null): AlertTrendRow[] {
  const records = alertData?.records ?? []
  const byDate: Record<string, AlertTrendRow> = {}

  for (const record of records) {
    const date = record.event_ts.slice(0, 10)
    if (!byDate[date]) byDate[date] = { date, high: 0, medium: 0, low: 0 }
    byDate[date][record.severity]++
  }

  return Object.values(byDate).sort((left, right) => left.date.localeCompare(right.date))
}

const QUEUE_SLA_SECONDS = 120

export function buildQueueStatusRows(queueData: QueueAnalyticsData | null): QueueStatusRow[] {
  return (queueData?.zone_stats ?? []).map((zone) => ({
    ...zone,
    status: (zone.avg_wait_sec > QUEUE_SLA_SECONDS
      ? 'critical'
      : zone.avg_wait_sec > 60
        ? 'warning'
        : 'normal') as BadgeStatus,
  }))
}

export function buildZoneInsights(topZones: TopZonePoint[]): string[] {
  if (topZones.length === 0) return ['No zone-level historical activity is available yet.']
  const leader = topZones[0]
  const weakest = topZones[topZones.length - 1]
  return [
    `${leader.zone_name} leads zone traffic with ${formatNumber(leader.visitors)} unique visitors.`,
    `${leader.share.toFixed(1)}% of zone visitors are concentrated in the top zone.`,
    `${weakest.zone_name} has the lowest visible visitor volume in the current range.`,
  ]
}

export { QUEUE_SLA_SECONDS }
