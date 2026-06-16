import { StatusBadge } from '../../../shared/components/ui/StatusBadge'
import { SectionCard } from '../../../shared/components/ui/SectionCard'
import { EmptyState } from '../../../shared/components/ui/EmptyState'
import { formatDurationMs } from '../../../shared/utils/format'
import type { ZoneCount } from '../types'
import type { BadgeStatus } from '../../../shared/components/ui/StatusBadge'

type QueueStatusTableProps = {
  zoneCounts: ZoneCount[]
}

function queueStatus(zone: ZoneCount): BadgeStatus {
  const maxWaitSec = (zone.max_wait_ms ?? 0) / 1000
  if (maxWaitSec > 120 || zone.count >= 5) return 'critical'
  if (maxWaitSec > 60 || zone.count >= 3) return 'warning'
  return 'normal'
}

function queueAction(status: BadgeStatus): string {
  if (status === 'critical') return 'Open lane'
  if (status === 'warning') return 'Monitor'
  return '—'
}

export function QueueStatusTable({ zoneCounts }: QueueStatusTableProps) {
  const queueZones = zoneCounts.filter((z) => z.zone_type === 'queue')

  return (
    <SectionCard title="Queue Status" subtitle="Realtime per-zone breakdown">
      {queueZones.length === 0 ? (
        <EmptyState title="No queue zones" description="Queue zone data not available for this camera" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">
                <th className="pb-2 pr-4">Zone</th>
                <th className="pb-2 pr-4">People</th>
                <th className="pb-2 pr-4">Avg wait</th>
                <th className="pb-2 pr-4">Max wait</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {queueZones.map((zone) => {
                const status = queueStatus(zone)
                return (
                  <tr key={zone.zone_id} className="border-b border-slate-50">
                    <td className="py-2 pr-4 font-medium text-slate-800">
                      {zone.zone_name ?? zone.zone_id}
                    </td>
                    <td className="py-2 pr-4 text-slate-700">{zone.count}</td>
                    <td className="py-2 pr-4 text-slate-500">
                      {zone.avg_wait_ms != null && zone.avg_wait_ms > 0
                        ? formatDurationMs(zone.avg_wait_ms)
                        : '—'}
                    </td>
                    <td className="py-2 pr-4 text-slate-500">
                      {zone.max_wait_ms != null && zone.max_wait_ms > 0
                        ? formatDurationMs(zone.max_wait_ms)
                        : '—'}
                    </td>
                    <td className="py-2 pr-4">
                      <StatusBadge status={status} />
                    </td>
                    <td className="py-2 text-xs font-medium text-slate-600">
                      {queueAction(status)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  )
}
