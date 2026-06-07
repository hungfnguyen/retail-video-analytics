import { ArrowLeftRight, Clock, MapPinned, Users } from 'lucide-react'
import type { LineCrossing, ZoneCount } from '../types'

type ZoneRuntimePanelProps = {
  lineCrossings: LineCrossing[]
  zoneCounts: ZoneCount[]
}

function formatZoneType(zoneType: string) {
  return zoneType.replace(/_/g, ' ')
}

function zoneTone(zoneType: string) {
  if (zoneType === 'queue') {
    return 'bg-amber-50 text-amber-700 ring-amber-200'
  }

  if (zoneType === 'entrance') {
    return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  }

  if (zoneType === 'aisle') {
    return 'bg-blue-50 text-blue-700 ring-blue-200'
  }

  return 'bg-slate-100 text-slate-700 ring-slate-200'
}

function displayZoneName(zone: ZoneCount) {
  return zone.zone_name || zone.zone_id.replace(/_/g, ' ')
}

function formatDuration(totalSeconds = 0) {
  const safeSeconds = Math.max(0, Math.round(totalSeconds))
  const minutes = Math.floor(safeSeconds / 60)
  const seconds = safeSeconds % 60

  if (minutes > 0) {
    return `${minutes}m ${seconds.toString().padStart(2, '0')}s`
  }

  return `${seconds}s`
}

function shouldShowQueueWait(zone: ZoneCount) {
  return zone.zone_type === 'queue' && zone.count > 0
}

export function ZoneRuntimePanel({ lineCrossings, zoneCounts }: ZoneRuntimePanelProps) {
  const totalInZones = zoneCounts.reduce((sum, zone) => sum + Math.max(0, zone.count), 0)
  const sortedZones = [...zoneCounts].sort((a, b) => {
    if (b.count !== a.count) {
      return b.count - a.count
    }
    return a.zone_id.localeCompare(b.zone_id)
  })

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
      <div className="mb-3.5 flex items-start justify-between gap-3">
        <div>
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Retail zones</h2>
          <p className="m-0 mt-1 text-sm text-slate-500">Current zone occupancy</p>
        </div>
        <div className="flex items-center gap-2 rounded-md bg-slate-100 px-3 py-2 text-sm font-bold text-slate-700">
          <Users size={16} />
          {totalInZones}
        </div>
      </div>

      {sortedZones.length > 0 ? (
        <div className="divide-y divide-slate-100">
          {sortedZones.map((zone) => (
            <div className="grid grid-cols-[1fr_auto] items-center gap-4 py-3" key={zone.zone_id}>
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  <MapPinned className="shrink-0 text-slate-400" size={16} />
                  <span className="truncate font-semibold text-slate-900">{displayZoneName(zone)}</span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold capitalize ring-1 ${zoneTone(zone.zone_type)}`}>
                    {formatZoneType(zone.zone_type)}
                  </span>
                </div>
                <div className="mt-1 truncate text-xs text-slate-500">
                  {zone.global_track_ids && zone.global_track_ids.length > 0
                    ? zone.global_track_ids.join(', ')
                    : zone.zone_id}
                </div>
                {shouldShowQueueWait(zone) && (
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-semibold text-amber-700">
                    <span className="inline-flex items-center gap-1">
                      <Clock size={12} />
                      Max wait {formatDuration(zone.max_wait_seconds)}
                    </span>
                    <span>Avg {formatDuration(zone.avg_wait_seconds)}</span>
                  </div>
                )}
              </div>
              <strong className="min-w-10 text-right text-2xl leading-none text-blue-600">{zone.count}</strong>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid min-h-32 place-items-center rounded-md border border-dashed border-slate-200 text-sm text-slate-500">
          No zone data
        </div>
      )}

      <div className="mt-4 border-t border-slate-100 pt-3">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
          <ArrowLeftRight size={15} />
          Line crossings
        </div>
        {lineCrossings.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {lineCrossings.slice(0, 6).map((crossing, index) => (
              <span
                className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700"
                key={`${crossing.line_id}-${crossing.global_track_id ?? crossing.track_id ?? index}-${index}`}
              >
                {crossing.line_id}: {crossing.direction}
              </span>
            ))}
          </div>
        ) : (
          <p className="m-0 text-sm text-slate-500">No recent crossings</p>
        )}
      </div>
    </section>
  )
}
