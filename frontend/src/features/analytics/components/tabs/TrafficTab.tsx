import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SectionCard } from '../../../../shared/components/ui/SectionCard'
import { EmptyState } from '../../../../shared/components/ui/EmptyState'
import { buildDailySummary, buildVisitorsTrend } from '../../adapters/analyticsViewModels'
import { formatDuration, formatNumber } from '../../../../shared/utils/format'
import type { AnalyticsDashboardData } from '../../types'

type TrafficTabProps = {
  data: AnalyticsDashboardData
}

export function TrafficTab({ data }: TrafficTabProps) {
  const trend = buildVisitorsTrend(data)
  const summary = buildDailySummary(data)

  return (
    <div className="grid gap-5 pt-5">
      <div className="grid grid-cols-[1.2fr_0.8fr] gap-5">
        <SectionCard
          title="Visitors by Hour"
          subtitle="Footfall pattern across the selected date range"
          badge={<span className="rounded-md bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">{data.range_label}</span>}
        >
          {trend.length === 0 ? (
            <EmptyState title="No hourly traffic data" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer height="100%" width="100%">
                <ComposedChart data={trend}>
                  <CartesianGrid stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="label" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis tickLine={false} width={44} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => formatNumber(Number(v))} isAnimationActive={false} />
                  <Bar dataKey="visitors" fill="#2563eb" name="Visitor events" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  <Line dataKey="average" dot={false} isAnimationActive={false} name="Per-day avg" stroke="#059669" strokeDasharray="4 4" strokeWidth={2} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Area Coverage" subtitle="Visitor events per camera / area">
          {data.camera_comparison.length === 0 ? (
            <EmptyState title="No camera comparison data" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={data.camera_comparison} layout="vertical">
                  <CartesianGrid stroke="#e2e8f0" horizontal={false} />
                  <XAxis type="number" tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis dataKey="camera_id" type="category" tickLine={false} width={68} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => formatNumber(Number(v))} isAnimationActive={false} />
                  <Bar dataKey="detections" name="Visitor events" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                    {data.camera_comparison.map((item, i) => (
                      <Cell fill={i === 0 ? '#0f766e' : i === 1 ? '#14b8a6' : '#5eead4'} key={item.camera_id} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Daily Summary"
        subtitle="Per-day visitor and dwell breakdown"
        badge={<span className="rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">Gold daily</span>}
      >
        {summary.length === 0 ? (
          <EmptyState title="No daily summary data" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4 text-right">Visitor Events</th>
                  <th className="pb-2 pr-4 text-right">Peak Hour</th>
                  <th className="pb-2 text-right">Avg Dwell</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {summary.map((row) => (
                  <tr className="hover:bg-slate-50" key={row.date}>
                    <td className="py-2.5 pr-4 font-semibold text-blue-700">{row.date}</td>
                    <td className="py-2.5 pr-4 text-right text-slate-700">{formatNumber(row.visitors)}</td>
                    <td className="py-2.5 pr-4 text-right text-slate-600">{row.peakHour}</td>
                    <td className="py-2.5 text-right text-slate-600">{row.avgDwellSec > 0 ? formatDuration(row.avgDwellSec) : '—'}</td>
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
