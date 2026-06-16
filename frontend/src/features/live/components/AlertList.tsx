import { StatusBadge } from '../../../shared/components/ui/StatusBadge'
import { EmptyState } from '../../../shared/components/ui/EmptyState'
import { formatRelativeTime } from '../../../shared/utils/format'
import type { Alert } from '../types'
import type { BadgeStatus } from '../../../shared/components/ui/StatusBadge'

type AlertListProps = {
  alerts: Alert[]
  onAlertClick?: (alert: Alert) => void
}

export function AlertList({ alerts, onAlertClick }: AlertListProps) {
  return (
    <div>
      <div className="mb-2.5 flex items-center gap-2">
        <h3 className="text-sm font-semibold text-slate-800">Active Alerts</h3>
        {alerts.length > 0 && (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-600">
            {alerts.length}
          </span>
        )}
      </div>

      {alerts.length === 0 ? (
        <EmptyState title="No active alerts" />
      ) : (
        <div className="grid max-h-52 gap-2 overflow-y-auto pr-1">
          {alerts.map((alert) => (
            <article
              className={`grid grid-cols-[1fr_auto] items-start gap-3 rounded-lg border border-slate-200 bg-white p-3 ${
                onAlertClick ? 'cursor-pointer hover:bg-slate-50 transition-colors' : ''
              }`}
              key={alert.alert_id}
              onClick={() => onAlertClick?.(alert)}
            >
              <div className="min-w-0">
                <strong className="block text-sm text-slate-900">{alert.title}</strong>
                <span className="block text-xs text-slate-500">{alert.description}</span>
                <span className="block text-xs text-slate-400">{formatRelativeTime(alert.event_ts)}</span>
              </div>
              <StatusBadge status={alert.severity as BadgeStatus} />
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
