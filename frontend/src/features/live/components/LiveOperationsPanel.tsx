import { StatusBadge } from '../../../shared/components/ui/StatusBadge'
import { EmptyState } from '../../../shared/components/ui/EmptyState'
import { formatDurationMs } from '../../../shared/utils/format'
import { AlertList } from './AlertList'
import type { Alert, ZoneCount } from '../types'
import type { BadgeStatus } from '../../../shared/components/ui/StatusBadge'

type LiveOperationsPanelProps = {
  alerts: Alert[]
  zoneCounts: ZoneCount[]
  onAlertClick?: (alert: Alert) => void
}

function queueStatus(zone: ZoneCount): BadgeStatus {
  const maxWaitSec = (zone.max_wait_ms ?? 0) / 1000
  if (maxWaitSec > 120 || zone.count >= 5) return 'critical'
  if (maxWaitSec > 60 || zone.count >= 3) return 'warning'
  return 'normal'
}

function queueAction(status: BadgeStatus): string {
  if (status === 'critical') return 'Open another checkout lane'
  if (status === 'warning') return 'Monitor closely'
  return 'No action needed'
}

export function LiveOperationsPanel({ alerts, zoneCounts, onAlertClick }: LiveOperationsPanelProps) {
  const queueZones = zoneCounts.filter((z) => z.zone_type === 'queue')

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <AlertList alerts={alerts} onAlertClick={onAlertClick} />

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-800">Queue Status</h3>
        {queueZones.length === 0 ? (
          <EmptyState title="No queue zones detected" />
        ) : (
          <div className="grid gap-2">
            {queueZones.map((zone) => {
              const status = queueStatus(zone)
              return (
                <div key={zone.zone_id} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-800 truncate">
                      {zone.zone_name ?? zone.zone_id}
                    </span>
                    <StatusBadge status={status} />
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-xs text-slate-500">
                    <span>{zone.count} people</span>
                    {zone.max_wait_ms != null && zone.max_wait_ms > 0 && (
                      <span>Max wait: {formatDurationMs(zone.max_wait_ms)}</span>
                    )}
                  </div>
                  <p className="mt-1 text-xs font-medium text-slate-600">{queueAction(status)}</p>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
