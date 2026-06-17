import { Bell, Clock, TrendingUp, Users } from 'lucide-react'
import { StatusBadge } from '../../../shared/components/ui/StatusBadge'
import { EmptyState } from '../../../shared/components/ui/EmptyState'
import { formatRelativeTime } from '../../../shared/utils/format'
import type { Alert } from '../types'
import type { BadgeStatus } from '../../../shared/components/ui/StatusBadge'
import type { ComponentType } from 'react'

type AlertListProps = {
  alerts: Alert[]
  onAlertClick?: (alert: Alert) => void
}

function alertIcon(alertType: string): ComponentType<{ size?: number; className?: string }> {
  const t = alertType.toLowerCase()
  if (t.includes('wait') || t.includes('queue')) return Clock
  if (t.includes('density') || t.includes('crowd')) return Users
  if (t.includes('line') || t.includes('growing')) return TrendingUp
  return Bell
}

function alertIconStyle(severity: string): string {
  if (severity === 'high') return 'text-red-500 bg-red-50'
  if (severity === 'medium') return 'text-amber-500 bg-amber-50'
  return 'text-slate-400 bg-slate-50'
}

function formatAbsoluteTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function AlertList({ alerts, onAlertClick }: AlertListProps) {
  const sortedAlerts = [...alerts].sort((left, right) => {
    const severityRank = { high: 0, medium: 1, low: 2 }
    const statusRank = { new: 0, acknowledged: 1, resolved: 2 }
    const severityDelta = severityRank[left.severity] - severityRank[right.severity]
    if (severityDelta !== 0) return severityDelta
    const statusDelta = statusRank[left.status] - statusRank[right.status]
    if (statusDelta !== 0) return statusDelta
    return new Date(right.event_ts).getTime() - new Date(left.event_ts).getTime()
  })

  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Active Alerts</h3>
          {alerts.length > 0 && (
            <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-600">
              {alerts.length}
            </span>
          )}
        </div>
        <span className="text-xs font-medium text-blue-500 cursor-default">View all</span>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {sortedAlerts.length === 0 ? (
          <div className="flex h-full min-h-24 items-center justify-center">
            <EmptyState title="No active alerts" />
          </div>
        ) : (
          <div className="divide-y divide-slate-50">
            {sortedAlerts.map((alert) => {
              const Icon = alertIcon(alert.alert_type)
              const iconCls = alertIconStyle(alert.severity)
              return (
                <div
                  className={`flex items-start gap-3 px-4 py-3.5 ${onAlertClick ? 'cursor-pointer transition-colors hover:bg-slate-50' : ''}`}
                  key={alert.alert_id}
                  onClick={() => onAlertClick?.(alert)}
                >
                  <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${iconCls}`}>
                    <Icon size={14} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold leading-tight text-slate-900">{alert.title}</p>
                    <p className="mt-0.5 text-xs text-slate-500">{alert.zone || alert.camera_id}</p>
                    <div className="mt-1 flex items-center gap-2 text-xs text-slate-400">
                      <span>{formatAbsoluteTime(alert.event_ts)}</span>
                      <span>•</span>
                      <span>{formatRelativeTime(alert.event_ts)}</span>
                    </div>
                  </div>
                  <StatusBadge status={alert.severity as BadgeStatus} />
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
