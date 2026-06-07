import { memo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Clock, ShoppingCart, Timer, Users } from 'lucide-react'
import type { AnalyticsKpi, QueueAnalyticsData, QueueZoneStat } from '../types'

const toneClasses = {
  blue: { icon: 'bg-blue-50 text-blue-700 ring-blue-100', value: 'text-blue-700' },
  emerald: { icon: 'bg-emerald-50 text-emerald-700 ring-emerald-100', value: 'text-emerald-700' },
  amber: { icon: 'bg-amber-50 text-amber-700 ring-amber-100', value: 'text-amber-700' },
  violet: { icon: 'bg-violet-50 text-violet-700 ring-violet-100', value: 'text-violet-700' },
}

const kpiIcons = [Clock, Timer, Users, ShoppingCart]

function formatDuration(seconds: number) {
  if (seconds <= 0) return '0s'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`
}

function KpiCard({ kpi, index }: { kpi: AnalyticsKpi; index: number }) {
  const Icon = kpiIcons[index] ?? Clock
  const classes = toneClasses[kpi.tone]
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
      <div className="flex items-center gap-3">
        <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-lg ring-1 ${classes.icon}`}>
          <Icon size={23} />
        </span>
        <div className="min-w-0">
          <span className="block text-sm font-semibold text-slate-500">{kpi.label}</span>
          <span className={`block truncate text-2xl font-bold leading-tight ${classes.value}`}>{kpi.value}</span>
          <span className="block truncate text-xs text-slate-400">{kpi.meta}</span>
        </div>
      </div>
    </article>
  )
}

function ZoneStatsTable({ zones }: { zones: QueueZoneStat[] }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
      <h2 className="mb-3 text-[17px] font-bold text-slate-950">Queue zone breakdown</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <th className="pb-2 pr-4">Zone</th>
              <th className="pb-2 pr-4 text-right">Sessions</th>
              <th className="pb-2 pr-4 text-right">Avg wait</th>
              <th className="pb-2 pr-4 text-right">Max wait</th>
              <th className="pb-2 text-right">Unique visitors</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {zones.map((zone) => (
              <tr className="hover:bg-slate-50" key={zone.zone_id}>
                <td className="py-2.5 pr-4 font-semibold text-slate-800">
                  {zone.zone_id.replace(/_/g, ' ')}
                </td>
                <td className="py-2.5 pr-4 text-right text-slate-600">{zone.total_sessions.toLocaleString()}</td>
                <td className="py-2.5 pr-4 text-right font-semibold text-amber-600">
                  {formatDuration(zone.avg_wait_sec)}
                </td>
                <td className="py-2.5 pr-4 text-right text-rose-500">
                  {formatDuration(zone.max_wait_sec)}
                </td>
                <td className="py-2.5 text-right text-slate-600">{zone.unique_visitors.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function WaitTrendChart({ data }: { data: QueueAnalyticsData['wait_trend'] }) {
  const chartData = data.map((p) => ({
    hour: p.hour,
    avg_wait_min: Math.round((p.avg_wait_sec / 60) * 10) / 10,
    sessions: p.sessions,
  }))

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
      <h2 className="mb-1 text-[17px] font-bold text-slate-950">Avg wait by hour</h2>
      <p className="mb-3 text-xs text-slate-400">Minutes per queue session, grouped by hour of day</p>
      <div className="h-48">
        <ResponsiveContainer height={192} width="100%">
          <BarChart data={chartData} barSize={18}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="hour" tickLine={false} tick={{ fontSize: 11 }} />
            <YAxis tickLine={false} width={36} tick={{ fontSize: 11 }} unit="m" />
            <Tooltip
              isAnimationActive={false}
              formatter={(value: number) => [`${value}m`, 'Avg wait']}
            />
            <Bar dataKey="avg_wait_min" fill="#f59e0b" radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}

export const QueueAnalyticsPanels = memo(function QueueAnalyticsPanels({
  data,
}: {
  data: QueueAnalyticsData
}) {
  return (
    <div className="mt-8 border-t border-slate-200 pt-6">
      <div className="mb-4 flex items-center gap-2">
        <ShoppingCart className="text-amber-500" size={20} />
        <h2 className="m-0 text-xl font-bold text-slate-950">Queue Analytics</h2>
        <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-bold text-amber-600 ring-1 ring-amber-200">
          Gold lakehouse
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-5">
        {data.kpis.map((kpi, i) => (
          <KpiCard key={kpi.label} kpi={kpi} index={i} />
        ))}
      </div>

      {data.data_status === 'ready' ? (
        <div className="grid grid-cols-[1.1fr_0.9fr] gap-4">
          <ZoneStatsTable zones={data.zone_stats} />
          <WaitTrendChart data={data.wait_trend} />
        </div>
      ) : (
        <div className="grid min-h-40 place-items-center rounded-lg border border-dashed border-slate-200 bg-white text-sm text-slate-400">
          {data.data_status === 'error'
            ? `Query error: ${data.error_message}`
            : 'No queue sessions in Gold lakehouse yet — pipeline is warming up.'}
        </div>
      )}
    </div>
  )
})
