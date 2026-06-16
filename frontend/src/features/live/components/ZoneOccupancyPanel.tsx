import { SectionCard } from '../../../shared/components/ui/SectionCard'
import { EmptyState } from '../../../shared/components/ui/EmptyState'
import type { ZoneCount } from '../types'

type ZoneOccupancyPanelProps = {
  zoneCounts: ZoneCount[]
}

const zoneTypeBadge: Record<string, string> = {
  queue:    'bg-amber-100 text-amber-700',
  entrance: 'bg-blue-100 text-blue-700',
  exit:     'bg-slate-100 text-slate-600',
  display:  'bg-violet-100 text-violet-700',
}

export function ZoneOccupancyPanel({ zoneCounts }: ZoneOccupancyPanelProps) {
  const zones = [...zoneCounts]
    .filter((z) => z.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)

  const maxCount = zones.length > 0 ? Math.max(...zones.map((z) => z.count)) : 1

  return (
    <SectionCard title="Zone Occupancy" subtitle="People per zone right now">
      {zones.length === 0 ? (
        <EmptyState title="No zone data" description="No occupied zones detected" />
      ) : (
        <div className="grid gap-3">
          {zones.map((zone) => {
            const share = zone.count / Math.max(1, maxCount)
            const badgeCls = zoneTypeBadge[zone.zone_type] ?? 'bg-slate-100 text-slate-600'
            return (
              <div key={zone.zone_id}>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="truncate text-xs font-semibold text-slate-700">
                      {zone.zone_name ?? zone.zone_id}
                    </span>
                    <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${badgeCls}`}>
                      {zone.zone_type}
                    </span>
                  </div>
                  <span className="shrink-0 text-xs font-bold text-slate-800">{zone.count}</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-blue-500 transition-all duration-500"
                    style={{ width: `${share * 100}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </SectionCard>
  )
}
