import { EmptyState } from '../../../../shared/components/ui/EmptyState'
import { SectionCard } from '../../../../shared/components/ui/SectionCard'
import { formatNumber } from '../../../../shared/utils/format'
import { buildZoneInsights } from '../../adapters/analyticsViewModels'
import type { AnalyticsDashboardData } from '../../types'

type ZonesTabProps = {
  data: AnalyticsDashboardData
}

function occupancyTone(value: number) {
  if (value >= 70) return 'bg-red-500'
  if (value >= 45) return 'bg-amber-400'
  return 'bg-emerald-500'
}

export function ZonesTab({ data }: ZonesTabProps) {
  const zones = data.top_zones
  const insights = buildZoneInsights(zones)

  return (
    <div className="grid gap-5">
      <div className="grid grid-cols-[1.1fr_0.9fr] gap-5">
        <SectionCard title="Top Zones" subtitle="Highest visitor concentration across the selected period">
          {zones.length === 0 ? (
            <EmptyState title="No zone ranking available" />
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-[28px_minmax(0,1fr)_96px_96px] gap-4 border-b border-slate-100 pb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                <span>#</span>
                <span>Zone</span>
                <span className="text-right">Visitors</span>
                <span className="text-right">Share</span>
              </div>
              {zones.map((zone, index) => (
                <div className="grid grid-cols-[28px_minmax(0,1fr)_96px_96px] items-center gap-4" key={zone.zone_id}>
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600">
                    {index + 1}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-800">{zone.zone_name}</p>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.max(zone.share, 4)}%` }} />
                    </div>
                  </div>
                  <p className="text-right text-sm font-medium text-slate-700">{formatNumber(zone.visitors)}</p>
                  <p className="text-right text-sm text-slate-500">{zone.share.toFixed(1)}%</p>
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard title="Zone Insights" subtitle="Quick interpretation of current zone behavior">
          {zones.length === 0 ? (
            <EmptyState title="No zone insights yet" />
          ) : (
            <div className="space-y-4">
              {insights.map((insight) => (
                <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-700" key={insight}>
                  {insight}
                </div>
              ))}
              <div className="rounded-xl border border-slate-100 bg-white px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Best visible zone</p>
                <p className="mt-1 text-lg font-semibold text-slate-900">{zones[0].zone_name}</p>
                <p className="mt-1 text-sm text-slate-500">
                  Avg occupancy {zones[0].avg_occupancy.toFixed(1)} across {formatNumber(zones[0].occupied_minutes)} occupied minute(s).
                </p>
              </div>
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Zone Utilization" subtitle="Relative occupancy by zone">
        {zones.length === 0 ? (
          <EmptyState title="No zone utilization available" />
        ) : (
          <div className="space-y-4">
            {zones.map((zone) => (
              <div className="space-y-1.5" key={zone.zone_id}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-slate-800">{zone.zone_name}</p>
                    <p className="text-xs text-slate-500">{formatNumber(zone.occupied_minutes)} occupied minute(s)</p>
                  </div>
                  <p className="text-sm font-semibold text-slate-700">{zone.avg_occupancy.toFixed(0)}%</p>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full ${occupancyTone(zone.avg_occupancy)}`}
                    style={{ width: `${Math.min(zone.avg_occupancy, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  )
}
