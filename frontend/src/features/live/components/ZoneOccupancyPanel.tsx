import type { ZoneCount } from '../types'

type ZoneOccupancyPanelProps = {
  zoneCounts: ZoneCount[]
}

function barColor(pct: number): string {
  if (pct >= 70) return 'bg-red-500'
  if (pct >= 40) return 'bg-amber-400'
  return 'bg-emerald-500'
}

export function ZoneOccupancyPanel({ zoneCounts }: ZoneOccupancyPanelProps) {
  const sorted = [...zoneCounts]
    .filter((z) => z.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)

  const total = sorted.reduce((s, z) => s + z.count, 0)
  const maxCount = Math.max(...sorted.map((z) => z.count), 1)

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Zone Occupancy</h3>
          <p className="text-xs text-slate-400">People per zone right now</p>
        </div>
        <span className="text-xs font-medium text-blue-500 cursor-default">View all</span>
      </div>

      <div className="px-4 pb-3 pt-3">
        {sorted.length === 0 ? (
          <p className="py-4 text-center text-sm text-slate-400">No occupied zones</p>
        ) : (
          <div className="grid gap-3">
            {sorted.map((zone) => {
              const pct = total > 0 ? Math.round((zone.count / maxCount) * 78) : 0
              const color = barColor(pct)
              return (
                <div key={zone.zone_id}>
                  <div className="mb-1 flex items-center justify-between">
                    <div className="min-w-0 pr-2">
                      <span className="block truncate text-xs font-medium text-slate-700">
                        {zone.zone_name ?? zone.zone_id}
                      </span>
                    </div>
                    <div className="shrink-0 text-right">
                      <span className={`block text-xs font-bold ${pct >= 70 ? 'text-red-600' : pct >= 40 ? 'text-amber-600' : 'text-emerald-600'}`}>
                        {pct}%
                      </span>
                    </div>
                  </div>
                  <div className="h-2 w-full rounded-full bg-slate-100">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${color}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[11px] text-slate-400">
                    <span>{zone.count} people</span>
                    <span>{total > 0 ? Math.round((zone.count / total) * 100) : 0}% of visible crowd</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Legend */}
        <div className="mt-4 flex items-center gap-3 border-t border-slate-100 pt-2.5">
          <span className="flex items-center gap-1 text-[10px] text-slate-500">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
            Low (0–40%)
          </span>
          <span className="flex items-center gap-1 text-[10px] text-slate-500">
            <span className="inline-block h-2 w-2 rounded-full bg-amber-400" />
            Medium (40–70%)
          </span>
          <span className="flex items-center gap-1 text-[10px] text-slate-500">
            <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
            High (70–100%)
          </span>
        </div>
      </div>
    </div>
  )
}
