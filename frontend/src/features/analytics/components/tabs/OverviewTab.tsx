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
import { MetricCard } from '../../../../shared/components/ui/MetricCard'
import { SectionCard } from '../../../../shared/components/ui/SectionCard'
import { EmptyState } from '../../../../shared/components/ui/EmptyState'
import { buildOverviewKpis } from '../../adapters/analyticsViewModels'
import type { AlertHistoryData, AnalyticsDashboardData, QueueAnalyticsData } from '../../types'

type OverviewTabProps = {
  data: AnalyticsDashboardData | null
  queueData: QueueAnalyticsData | null
  alertData: AlertHistoryData | null
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const HEATMAP_HOURS = Array.from({ length: 17 }, (_, index) => index + 6)

function heatColor(value: number, maxValue: number) {
  if (maxValue <= 0) return '#eef2ff'
  const ratio = value / maxValue
  if (ratio >= 0.9) return '#ef4444'
  if (ratio >= 0.75) return '#f97316'
  if (ratio >= 0.55) return '#facc15'
  if (ratio >= 0.35) return '#86efac'
  if (ratio >= 0.18) return '#a5b4fc'
  return '#e9d5ff'
}

export function OverviewTab({ data, queueData, alertData }: OverviewTabProps) {
  const kpis = buildOverviewKpis(data, queueData, alertData)
  const trend = data?.visitors_over_time ?? []
  const weekdayData = data?.weekday_pattern ?? []
  const topZones = data?.top_zones ?? []
  const heatmap = data?.peak_hours_heatmap ?? []
  const heatMax = Math.max(...heatmap.map((cell) => cell.visitors), 0)

  const heatLookup = new Map(heatmap.map((cell) => [`${cell.weekday}-${cell.hour}`, cell.visitors]))

  return (
    <div className="grid gap-5">
      <div className="grid grid-cols-5 gap-4">
        {kpis.map((kpi) => (
          <MetricCard key={kpi.label} {...kpi} />
        ))}
      </div>

      <div className="grid grid-cols-2 gap-5">
        <SectionCard title="Visitors Over Time" subtitle="Traffic pattern across selected period">
          {trend.length === 0 ? (
            <EmptyState title="No traffic series yet" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer height="100%" width="100%">
                <LineChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke="#eef2ff" vertical={false} />
                  <XAxis dataKey="label" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={36} tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip isAnimationActive={false} formatter={(value) => [Number(value ?? 0).toLocaleString(), 'Visitors']} />
                  <Line dataKey="visitors" dot={{ r: 3, fill: '#4f46e5' }} isAnimationActive={false} stroke="#4f46e5" strokeWidth={3} type="monotone" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Visitors by Day of Week" subtitle="Average traffic per weekday">
          {weekdayData.length === 0 ? (
            <EmptyState title="Need at least one full day of traffic" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={weekdayData} margin={{ top: 8, right: 8, bottom: 0, left: -6 }}>
                  <CartesianGrid stroke="#eef2ff" vertical={false} />
                  <XAxis dataKey="weekday" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={36} tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip isAnimationActive={false} formatter={(value) => [Number(value ?? 0).toLocaleString(), 'Visitors']} />
                  <Bar dataKey="visitors" fill="#6d28d9" isAnimationActive={false} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>
      </div>

      <div className="grid grid-cols-[1.05fr_0.95fr] gap-5">
        <SectionCard
          title="Peak Hours (By Avg Visitors)"
          subtitle="Day-hour traffic concentration"
          actions={
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>Low</span>
              <div className="h-2 w-24 rounded-full bg-gradient-to-r from-violet-400 via-yellow-300 to-red-500" />
              <span>High</span>
            </div>
          }
        >
          {heatmap.length === 0 ? (
            <EmptyState title="No hourly density matrix yet" />
          ) : (
            <div className="grid gap-2">
              <div className="grid grid-cols-[46px_repeat(17,minmax(0,1fr))] gap-1 text-[10px] text-slate-400">
                <span />
                {HEATMAP_HOURS.map((hour) => (
                  <span className="text-center" key={hour}>
                    {String(hour).padStart(2, '0')}
                  </span>
                ))}
              </div>
              {WEEKDAYS.map((weekday) => (
                <div className="grid grid-cols-[46px_repeat(17,minmax(0,1fr))] gap-1" key={weekday}>
                  <div className="flex items-center text-xs font-medium text-slate-500">{weekday}</div>
                  {HEATMAP_HOURS.map((hour) => {
                    const value = heatLookup.get(`${weekday}-${hour}`) ?? 0
                    return (
                      <div
                        className="h-8 rounded-md border border-white"
                        key={`${weekday}-${hour}`}
                        style={{ backgroundColor: heatColor(value, heatMax) }}
                        title={`${weekday} ${String(hour).padStart(2, '0')}:00 — ${value.toLocaleString()} visitors`}
                      />
                    )
                  })}
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard title="Top Zones (By Visitors)" subtitle="Highest traffic concentration by zone">
          {topZones.length === 0 ? (
            <EmptyState title="No zone ranking available yet" />
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-[minmax(0,1fr)_92px_92px] gap-4 border-b border-slate-100 pb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                <span>Zone</span>
                <span className="text-right">Visitors</span>
                <span className="text-right">Share</span>
              </div>
              {topZones.map((zone) => (
                <div className="grid grid-cols-[minmax(0,1fr)_92px_92px] items-center gap-4" key={zone.zone_id}>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-800">{zone.zone_name}</p>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.max(zone.share, 4)}%` }} />
                    </div>
                  </div>
                  <p className="text-right text-sm font-medium text-slate-700">{zone.visitors.toLocaleString()}</p>
                  <p className="text-right text-sm text-slate-500">{zone.share.toFixed(1)}%</p>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  )
}
