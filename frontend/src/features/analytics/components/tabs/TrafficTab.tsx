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
import { SectionCard } from '../../../../shared/components/ui/SectionCard'
import { formatDuration, formatNumber } from '../../../../shared/utils/format'
import type { AnalyticsDashboardData } from '../../types'

type TrafficTabProps = {
  data: AnalyticsDashboardData
}

export function TrafficTab({ data }: TrafficTabProps) {
  const trend = data.visitors_over_time
  const hourly = data.hourly_traffic
  const summary = data.daily_summary

  return (
    <div className="grid gap-5">
      <div className="grid grid-cols-[1.2fr_0.8fr] gap-5">
        <SectionCard title="Traffic Trend" subtitle="Unique visitor volume across selected period">
          {trend.length === 0 ? (
            <EmptyState title="No traffic trend available" />
          ) : (
            <div className="h-72">
              <ResponsiveContainer height="100%" width="100%">
                <LineChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke="#eef2ff" vertical={false} />
                  <XAxis dataKey="label" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={40} tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip isAnimationActive={false} formatter={(value) => [formatNumber(Number(value ?? 0)), 'Visitors']} />
                  <Line dataKey="visitors" dot={false} isAnimationActive={false} stroke="#4f46e5" strokeWidth={3} type="monotone" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Peak Hour Distribution" subtitle="Average unique visitors by hour of day">
          {hourly.length === 0 ? (
            <EmptyState title="No hourly pattern available" />
          ) : (
            <div className="h-72">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={hourly} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                  <CartesianGrid stroke="#eef2ff" vertical={false} />
                  <XAxis dataKey="hour" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={38} tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip isAnimationActive={false} formatter={(value) => [formatNumber(Number(value ?? 0)), 'Visitors']} />
                  <Bar dataKey="avg_visitors" fill="#7c3aed" isAnimationActive={false} radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Daily Summary" subtitle="Business summary for each day in range">
        {summary.length === 0 ? (
          <EmptyState title="No daily summary available" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  <th className="pb-3 pr-4">Date</th>
                  <th className="pb-3 pr-4 text-right">Visitors</th>
                  <th className="pb-3 pr-4 text-right">Detections</th>
                  <th className="pb-3 pr-4 text-right">Peak Hour</th>
                  <th className="pb-3 pr-4 text-right">Avg Dwell</th>
                  <th className="pb-3 pr-4 text-right">Avg Queue Wait</th>
                  <th className="pb-3 text-right">Alerts</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {summary.map((row) => (
                  <tr className="hover:bg-slate-50" key={row.date}>
                    <td className="py-3 pr-4 font-medium text-slate-800">{row.date}</td>
                    <td className="py-3 pr-4 text-right text-slate-700">{formatNumber(row.visitors)}</td>
                    <td className="py-3 pr-4 text-right text-slate-600">{formatNumber(row.detections)}</td>
                    <td className="py-3 pr-4 text-right text-slate-600">{row.peak}</td>
                    <td className="py-3 pr-4 text-right text-slate-600">{row.avg_dwell_sec > 0 ? formatDuration(row.avg_dwell_sec) : '—'}</td>
                    <td className="py-3 pr-4 text-right text-slate-600">{row.avg_queue_wait_sec > 0 ? formatDuration(row.avg_queue_wait_sec) : '—'}</td>
                    <td className="py-3 text-right text-slate-600">{formatNumber(row.alerts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  )
}
