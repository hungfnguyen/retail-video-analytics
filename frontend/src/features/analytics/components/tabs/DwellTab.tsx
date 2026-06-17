import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { EmptyState } from '../../../../shared/components/ui/EmptyState'
import { MetricCard } from '../../../../shared/components/ui/MetricCard'
import { SectionCard } from '../../../../shared/components/ui/SectionCard'
import { formatDuration, formatNumber } from '../../../../shared/utils/format'
import type { AnalyticsDashboardData } from '../../types'

type DwellTabProps = {
  data: AnalyticsDashboardData
}

export function DwellTab({ data }: DwellTabProps) {
  const bands = data.dwell_bands
  const trend = data.dwell_trend
  const totalTracks = bands.reduce((sum, item) => sum + item.value, 0)
  const avgDwell = data.avg_dwell_sec
  const p90Dwell = Math.max(...trend.map((item) => item.p90_dwell_sec), 0)
  const longShare = totalTracks > 0
    ? Math.round(((bands.find((item) => item.label === 'Long')?.value ?? 0) / totalTracks) * 100)
    : 0

  return (
    <div className="grid gap-5">
      <div className="grid grid-cols-4 gap-4">
        <MetricCard label="Avg Dwell Time" value={avgDwell > 0 ? formatDuration(avgDwell) : '—'} tone="green" meta="Weighted across the selected period" />
        <MetricCard label="P90 Dwell" value={p90Dwell > 0 ? formatDuration(p90Dwell) : '—'} tone="amber" meta="Long-stay visitor threshold" />
        <MetricCard label="Long Dwell Share" value={`${longShare}%`} tone="violet" meta="Visitors with extended engagement" />
        <MetricCard label="Observed Visits" value={formatNumber(totalTracks)} tone="blue" meta="Derived from Gold dwell aggregates" />
      </div>

      <div className="grid grid-cols-[1.1fr_0.9fr] gap-5">
        <SectionCard title="Dwell Trend" subtitle="Average and percentile engagement over time">
          {trend.length === 0 ? (
            <EmptyState title="No dwell trend available" />
          ) : (
            <div className="h-72">
              <ResponsiveContainer height="100%" width="100%">
                <LineChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke="#eef2ff" vertical={false} />
                  <XAxis dataKey="date" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={44} tick={{ fontSize: 11 }} />
                  <Tooltip
                    isAnimationActive={false}
                    formatter={(value, name) => [formatDuration(Number(value ?? 0)), String(name)]}
                  />
                  <Line dataKey="avg_dwell_sec" dot={false} isAnimationActive={false} name="Avg dwell" stroke="#10b981" strokeWidth={3} type="monotone" />
                  <Line dataKey="p50_dwell_sec" dot={false} isAnimationActive={false} name="P50 dwell" stroke="#6366f1" strokeWidth={2} type="monotone" />
                  <Line dataKey="p90_dwell_sec" dot={false} isAnimationActive={false} name="P90 dwell" stroke="#f59e0b" strokeWidth={2} type="monotone" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Dwell Segments" subtitle="Short, medium, and long engagement mix">
          {bands.length === 0 ? (
            <EmptyState title="No dwell segment data" />
          ) : (
            <div className="h-72">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={bands} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                  <CartesianGrid stroke="#eef2ff" vertical={false} />
                  <XAxis dataKey="label" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={36} tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip isAnimationActive={false} formatter={(value) => [formatNumber(Number(value ?? 0)), 'Visits']} />
                  <Bar dataKey="value" fill="#8b5cf6" isAnimationActive={false} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  )
}
