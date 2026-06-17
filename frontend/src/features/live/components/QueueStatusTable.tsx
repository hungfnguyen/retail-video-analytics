import { ShoppingCart, TrendingUp } from 'lucide-react'
import { StatusBadge } from '../../../shared/components/ui/StatusBadge'
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

function queueTrend(status: BadgeStatus): string {
  if (status === 'critical') return 'text-red-500'
  if (status === 'warning') return 'text-amber-500'
  return 'text-emerald-500'
}

export function QueueStatusTable({ zoneCounts }: QueueStatusTableProps) {
  const queueZones = zoneCounts
    .filter((z) => z.zone_type === 'queue')
    .sort((a, b) => (b.max_wait_ms ?? 0) - (a.max_wait_ms ?? 0))

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Queue Status</h3>
          <p className="text-xs text-slate-400">Realtime per-zone breakdown</p>
        </div>
        <span className="text-xs font-medium text-blue-500 cursor-default">View all</span>
      </div>

      <div className="px-4 pb-4 pt-3">
        {queueZones.length === 0 ? (
          <EmptyState title="No queue zones" description="No queue zones detected for this camera" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                <th className="pb-2 pr-3">Zone</th>
                <th className="pb-2 pr-3 text-right">Avg Wait</th>
                <th className="pb-2 pr-3 text-right">Max Wait</th>
                <th className="pb-2 pr-3">Status</th>
                <th className="pb-2 text-right">Trend</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {queueZones.map((zone) => {
                const status = queueStatus(zone)
                return (
                  <tr key={zone.zone_id}>
                    <td className="py-2.5 pr-3">
                      <div className="flex items-center gap-2">
                        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-50">
                          <ShoppingCart size={11} className="text-amber-500" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-xs font-semibold text-slate-800">
                            {zone.zone_name ?? zone.zone_id}
                          </p>
                          <p className="text-[10px] text-slate-400">{zone.count} people</p>
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 pr-3 text-right text-xs font-medium text-amber-600">
                      {zone.avg_wait_ms != null && zone.avg_wait_ms > 0
                        ? formatDurationMs(zone.avg_wait_ms)
                        : '—'}
                    </td>
                    <td className="py-2.5 pr-3 text-right text-xs font-medium text-rose-500">
                      {zone.max_wait_ms != null && zone.max_wait_ms > 0
                        ? formatDurationMs(zone.max_wait_ms)
                        : '—'}
                    </td>
                    <td className="py-2.5 pr-3">
                      <StatusBadge status={status} />
                    </td>
                    <td className="py-2.5 text-right">
                      <TrendingUp size={14} className={`ml-auto ${queueTrend(status)}`} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
