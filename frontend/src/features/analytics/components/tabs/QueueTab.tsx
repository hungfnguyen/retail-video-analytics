import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { MetricCard } from '../../../../shared/components/ui/MetricCard'
import { SectionCard } from '../../../../shared/components/ui/SectionCard'
import { StatusBadge } from '../../../../shared/components/ui/StatusBadge'
import { EmptyState } from '../../../../shared/components/ui/EmptyState'
import { buildQueueStatusRows, QUEUE_SLA_SECONDS } from '../../adapters/analyticsViewModels'
import { formatDuration, formatNumber } from '../../../../shared/utils/format'
import type { QueueAnalyticsData } from '../../types'

type QueueTabProps = {
  data: QueueAnalyticsData
}

export function QueueTab({ data }: QueueTabProps) {
  const rows = buildQueueStatusRows(data)
  const violations = rows.filter((r) => r.avg_wait_sec > QUEUE_SLA_SECONDS).length
  const totalSessions = rows.reduce((s, r) => s + r.total_sessions, 0)
  const weightedAvg = totalSessions > 0
    ? rows.reduce((acc, r) => acc + r.avg_wait_sec * r.total_sessions, 0) / totalSessions
    : 0

  const trendData = data.wait_trend.map((p) => ({
    hour: p.hour,
    avg_wait_min: Math.round((p.avg_wait_sec / 60) * 10) / 10,
    sessions: p.sessions,
  }))

  return (
    <div className="grid gap-5 pt-5">
      {/* KPI row */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard label="Total Queue Sessions" value={formatNumber(totalSessions)} tone="blue" />
        <MetricCard label="Avg Queue Wait" value={weightedAvg > 0 ? formatDuration(weightedAvg) : '—'} tone={weightedAvg > QUEUE_SLA_SECONDS ? 'red' : weightedAvg > 60 ? 'amber' : 'green'} />
        <MetricCard label="SLA Violations" value={violations} tone={violations > 0 ? 'red' : 'green'} meta={`SLA threshold: ${QUEUE_SLA_SECONDS}s`} />
        <MetricCard label="Queue Zones" value={rows.length} tone="slate" />
      </div>

      <div className="grid grid-cols-[1fr_0.7fr] gap-5">
        {/* Zone breakdown table */}
        <SectionCard title="Queue Zone Breakdown" subtitle="Per-zone session and wait stats">
          {rows.length === 0 ? (
            <EmptyState title="No queue zone data" description="Gold queue tables are empty — pipeline warming up" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <th className="pb-2 pr-4">Zone</th>
                    <th className="pb-2 pr-4 text-right">Sessions</th>
                    <th className="pb-2 pr-4 text-right">Avg wait</th>
                    <th className="pb-2 pr-4 text-right">Max wait</th>
                    <th className="pb-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {rows.map((row) => (
                    <tr className="hover:bg-slate-50" key={row.zone_id}>
                      <td className="py-2.5 pr-4 font-semibold text-slate-800">
                        {row.zone_id.replace(/_/g, ' ')}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-slate-600">{row.total_sessions.toLocaleString()}</td>
                      <td className="py-2.5 pr-4 text-right font-semibold text-amber-600">
                        {formatDuration(row.avg_wait_sec)}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-rose-500">
                        {formatDuration(row.max_wait_sec)}
                      </td>
                      <td className="py-2.5">
                        <StatusBadge status={row.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>

        {/* Wait trend chart */}
        <SectionCard title="Avg Wait by Hour" subtitle="Minutes per session, grouped by hour">
          {trendData.length === 0 ? (
            <EmptyState title="No trend data" />
          ) : (
            <div className="h-52">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={trendData} barSize={16}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="hour" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={36} tick={{ fontSize: 11 }} unit="m" />
                  <Tooltip isAnimationActive={false} formatter={(v) => [String(Number(v)) + 'm', 'Avg wait']} />
                  <Bar dataKey="avg_wait_min" fill="#f59e0b" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  )
}
