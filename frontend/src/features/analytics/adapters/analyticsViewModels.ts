import type { MetricCardProps } from '../../../shared/components/ui/MetricCard'
import { formatDuration, formatNumber } from '../../../shared/utils/format'
import type {
  AlertHistoryData,
  AlertHistoryRecord,
  AnalyticsDashboardData,
  QueueAnalyticsData,
  QueueZoneStat,
} from '../types'
import type { BadgeStatus } from '../../../shared/components/ui/StatusBadge'

export type QueueStatusRow = QueueZoneStat & { status: BadgeStatus }

export type AlertTrendRow = { date: string; high: number; medium: number; low: number }

// ---------------------------------------------------------------------------
// Overview KPIs — derived from raw fields, NOT from backend kpis[]
// ---------------------------------------------------------------------------
export function buildOverviewKpis(
  data: AnalyticsDashboardData | null,
  queueData: QueueAnalyticsData | null,
  alertData: AlertHistoryData | null,
): MetricCardProps[] {
  const totalVisitors = data?.daily_summary.reduce((s, r) => s + r.detections, 0) ?? 0

  const peakHour = data?.hourly_traffic.length
    ? data.hourly_traffic.reduce((best, p) => (p.detections > best.detections ? p : best)).hour
    : null

  const weightedDwell =
    data?.daily_summary.reduce((acc, r) => acc + r.avg_dwell_sec * r.detections, 0) ?? 0
  const totalDetForDwell = data?.daily_summary.reduce((s, r) => s + r.detections, 0) ?? 0
  const avgDwellSec = totalDetForDwell > 0 ? weightedDwell / totalDetForDwell : 0

  const queueWeightedWait =
    queueData?.zone_stats.reduce((acc, z) => acc + z.avg_wait_sec * z.total_sessions, 0) ?? 0
  const queueTotalSessions = queueData?.zone_stats.reduce((s, z) => s + z.total_sessions, 0) ?? 0
  const avgQueueWaitSec = queueTotalSessions > 0 ? queueWeightedWait / queueTotalSessions : 0

  const alertTotal = alertData?.records.length ?? 0
  const highAlerts = alertData?.records.filter((r) => r.severity === 'high').length ?? 0

  return [
    {
      label: 'Visitor Observations',
      value: formatNumber(totalVisitors),
      tone: 'blue',
      meta: data?.range_label ?? '—',
    },
    {
      label: 'Peak Hour',
      value: peakHour ?? '—',
      tone: 'violet',
      meta: 'Hour with most traffic',
    },
    {
      label: 'Avg Dwell Time',
      value: avgDwellSec > 0 ? formatDuration(avgDwellSec) : '—',
      tone: 'green',
      meta: 'Weighted by daily visitors',
    },
    {
      label: 'Avg Queue Wait',
      value: avgQueueWaitSec > 0 ? formatDuration(avgQueueWaitSec) : '—',
      tone: avgQueueWaitSec > 120 ? 'red' : avgQueueWaitSec > 60 ? 'amber' : 'green',
      meta: queueTotalSessions > 0 ? `${queueTotalSessions.toLocaleString()} sessions` : 'No queue data',
    },
    {
      label: 'Alerts',
      value: alertTotal,
      tone: highAlerts > 0 ? 'red' : alertTotal > 0 ? 'amber' : 'green',
      meta: highAlerts > 0 ? `${highAlerts} high severity` : 'No high severity',
    },
  ]
}

// ---------------------------------------------------------------------------
// Visitors trend — from hourly_traffic
// ---------------------------------------------------------------------------
export function buildVisitorsTrend(
  data: AnalyticsDashboardData | null,
): Array<{ label: string; visitors: number; average: number }> {
  return (data?.hourly_traffic ?? []).map((p) => ({
    label: p.hour,
    visitors: p.detections,
    average: p.average,
  }))
}

// ---------------------------------------------------------------------------
// Daily summary — remove avg_confidence column, relabel
// ---------------------------------------------------------------------------
export function buildDailySummary(
  data: AnalyticsDashboardData | null,
): Array<{ date: string; visitors: number; peakHour: string; avgDwellSec: number }> {
  return (data?.daily_summary ?? []).map((r) => ({
    date: r.date,
    visitors: r.detections,
    peakHour: r.peak,
    avgDwellSec: r.avg_dwell_sec,
  }))
}

// ---------------------------------------------------------------------------
// Alert KPIs — derived from records[]
// ---------------------------------------------------------------------------
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
    { label: 'Total Alerts', value: total, tone: total > 0 ? 'amber' : 'green' },
    { label: 'High Severity', value: high, tone: high > 0 ? 'red' : 'green' },
    { label: 'Most Common Type', value: mostCommonType.replace(/_/g, ' '), tone: 'violet', meta: `${typeCounts[mostCommonType] ?? 0} occurrences` },
    { label: 'Most Affected Zone', value: mostAffectedZone.replace(/_/g, ' '), tone: 'slate', meta: `${zoneCounts[mostAffectedZone] ?? 0} alerts` },
  ]
}

// ---------------------------------------------------------------------------
// Alert trend by day — aggregate records[] client-side
// ---------------------------------------------------------------------------
export function buildAlertTrendByDay(alertData: AlertHistoryData | null): AlertTrendRow[] {
  const records: AlertHistoryRecord[] = alertData?.records ?? []
  const byDate: Record<string, AlertTrendRow> = {}

  for (const r of records) {
    const date = r.event_ts.slice(0, 10)
    if (!byDate[date]) byDate[date] = { date, high: 0, medium: 0, low: 0 }
    byDate[date][r.severity]++
  }

  return Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date))
}

// ---------------------------------------------------------------------------
// Queue status rows — zone_stats + derived status
// ---------------------------------------------------------------------------
const QUEUE_SLA_SECONDS = 120

export function buildQueueStatusRows(queueData: QueueAnalyticsData | null): QueueStatusRow[] {
  return (queueData?.zone_stats ?? []).map((z) => ({
    ...z,
    status: (z.avg_wait_sec > QUEUE_SLA_SECONDS
      ? 'critical'
      : z.avg_wait_sec > 60
        ? 'warning'
        : 'normal') as BadgeStatus,
  }))
}

export { QUEUE_SLA_SECONDS }
