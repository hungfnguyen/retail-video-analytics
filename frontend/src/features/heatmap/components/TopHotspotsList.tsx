import { getTopHotspots } from '../adapters/heatmapViewModels'
import type { PresenceHeatmapData } from '../../analytics/types'

type TopHotspotsListProps = {
  data: PresenceHeatmapData | null
}

const intensityClasses = {
  low:    'bg-slate-100 text-slate-600',
  medium: 'bg-amber-100 text-amber-700',
  high:   'bg-red-100 text-red-700',
}

export function TopHotspotsList({ data }: TopHotspotsListProps) {
  const hotspots = getTopHotspots(data, 5)

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Top Hot Zones</h3>
      {hotspots.length === 0 ? (
        <p className="text-xs text-slate-400">No hotspot data</p>
      ) : (
        <div className="grid gap-2">
          {hotspots.map((spot, i) => {
            const maxValue = hotspots[0].value
            const share = maxValue > 0 ? spot.value / maxValue : 0
            return (
              <div key={spot.id}>
                <div className="mb-1 flex items-center gap-2">
                  <span className="w-4 text-center text-[11px] font-bold text-slate-400">{i + 1}</span>
                  <span className="flex-1 text-xs font-medium text-slate-700 capitalize">{spot.label}</span>
                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${intensityClasses[spot.intensity]}`}>
                    {spot.intensity}
                  </span>
                </div>
                <div className="ml-6 h-1.5 w-full rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-orange-400 transition-all duration-500"
                    style={{ width: `${share * 100}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
