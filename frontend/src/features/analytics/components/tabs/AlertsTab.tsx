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
import { buildAlertKpis, buildAlertTrendByDay } from '../../adapters/analyticsViewModels'
import { formatTimestamp } from '../../../../shared/utils/format'
import type { AlertHistoryData } from '../../types'
import type { BadgeStatus } from '../../../../shared/components/ui/StatusBadge'

type AlertsTabProps = {
  data: AlertHistoryData
}

export function AlertsTab({ data }: AlertsTabProps) {
  const kpis = buildAlertKpis(data)
  const trend = buildAlertTrendByDay(data)

  return (
    <div className="grid gap-5">
      <div className="grid grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <MetricCard key={kpi.label} {...kpi} />
        ))}
      </div>

      <div className="grid grid-cols-[0.7fr_1.3fr] gap-5">
        <SectionCard title="Alert Trend" subtitle="Daily count by severity">
          {trend.length === 0 ? (
            <EmptyState title="No trend data" />
          ) : (
            <div className="h-56">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={trend}>
                  <CartesianGrid stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="date" tickLine={false} tick={{ fontSize: 10 }} />
                  <YAxis tickLine={false} width={28} tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip isAnimationActive={false} />
                  <Bar dataKey="high" stackId="a" fill="#ef4444" name="High" isAnimationActive={false} />
                  <Bar dataKey="medium" stackId="a" fill="#f97316" name="Medium" isAnimationActive={false} />
                  <Bar dataKey="low" stackId="a" fill="#22c55e" name="Low" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Alert History" subtitle={`${data.records.length} incident(s) in the selected period`}>
          {data.records.length === 0 ? (
            <EmptyState
              title="No alert history"
              description="Alerts appear once Gold alerts pipeline is running and clip alerts are enabled."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <th className="pb-2 pr-4">Time</th>
                    <th className="pb-2 pr-4">Alert</th>
                    <th className="pb-2 pr-4">Camera</th>
                    <th className="pb-2 pr-4">Zone</th>
                    <th className="pb-2">Severity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {data.records.map((r) => (
                    <tr className="hover:bg-slate-50" key={r.alert_id}>
                      <td className="py-3 pr-4 text-xs text-slate-500">{formatTimestamp(r.event_ts)}</td>
                      <td className="py-3 pr-4">
                        <p className="font-semibold text-slate-800">{r.title}</p>
                        <p className="mt-0.5 text-xs text-slate-500">{r.description}</p>
                      </td>
                      <td className="py-2.5 pr-4 text-xs text-slate-600">{r.camera_id}</td>
                      <td className="py-2.5 pr-4 text-xs text-slate-500">{r.zone.replace(/_/g, ' ')}</td>
                      <td className="py-2.5">
                        <StatusBadge status={r.severity as BadgeStatus} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  )
}
