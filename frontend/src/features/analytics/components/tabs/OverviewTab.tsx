import {
  CartesianGrid,
  ComposedChart,
  Line,
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { MetricCard } from '../../../../shared/components/ui/MetricCard'
import { SectionCard } from '../../../../shared/components/ui/SectionCard'
import { EmptyState } from '../../../../shared/components/ui/EmptyState'
import { buildOverviewKpis, buildVisitorsTrend } from '../../adapters/analyticsViewModels'
import type { AlertHistoryData, AnalyticsDashboardData, QueueAnalyticsData } from '../../types'

type OverviewTabProps = {
  data: AnalyticsDashboardData | null
  queueData: QueueAnalyticsData | null
  alertData: AlertHistoryData | null
}

export function OverviewTab({ data, queueData, alertData }: OverviewTabProps) {
  const kpis = buildOverviewKpis(data, queueData, alertData)
  const trend = buildVisitorsTrend(data)

  const weekdayData =
    data && data.daily_summary.length >= 7
      ? (() => {
          const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
          const acc: Record<string, { total: number; count: number }> = {}
          for (const r of data.daily_summary) {
            const day = DAYS[new Date(r.date).getDay()]
            if (!acc[day]) acc[day] = { total: 0, count: 0 }
            acc[day].total += r.detections
            acc[day].count++
          }
          return DAYS.map((d) => ({ day: d, avg: acc[d] ? Math.round(acc[d].total / acc[d].count) : 0 }))
        })()
      : null

  return (
    <div className="grid gap-5 pt-5">
      {/* KPI row */}
      <div className="grid grid-cols-5 gap-3">
        {kpis.map((kpi) => (
          <MetricCard key={kpi.label} {...kpi} />
        ))}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-2 gap-5">
        <SectionCard title="Visitor Trend" subtitle="Observations by hour across date range">
          {trend.length === 0 ? (
            <EmptyState title="No hourly traffic data" />
          ) : (
            <div className="h-52">
              <ResponsiveContainer height="100%" width="100%">
                <ComposedChart data={trend}>
                  <CartesianGrid stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="label" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={40} tick={{ fontSize: 11 }} />
                  <Tooltip isAnimationActive={false} />
                  <Bar dataKey="visitors" fill="#2563eb" name="Visitors" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  <Line dataKey="average" dot={false} isAnimationActive={false} name="Daily avg" stroke="#059669" strokeDasharray="4 4" strokeWidth={2} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Day of Week Pattern" subtitle="Average visitors per weekday">
          {weekdayData === null ? (
            <EmptyState title="Needs ≥ 7 days" description="Select Last 7 days or more to see weekday patterns" />
          ) : (
            <div className="h-52">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={weekdayData}>
                  <CartesianGrid stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="day" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={40} tick={{ fontSize: 11 }} />
                  <Tooltip isAnimationActive={false} />
                  <Bar dataKey="avg" fill="#7c3aed" name="Avg visitors" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  )
}
