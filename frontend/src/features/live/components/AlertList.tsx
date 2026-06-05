import type { Alert } from '../types'

type AlertListProps = {
  alerts: Alert[]
}

const severityLabels = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

function formatEventTime(value: string) {
  const eventTime = new Date(value)
  if (Number.isNaN(eventTime.getTime())) {
    return 'Unknown time'
  }

  return eventTime.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function severityClassName(severity: Alert['severity']) {
  if (severity === 'high') {
    return 'bg-red-100 text-red-600'
  }

  if (severity === 'medium') {
    return 'bg-orange-100 text-orange-700'
  }

  return 'bg-amber-100 text-amber-700'
}

export function AlertList({ alerts }: AlertListProps) {
  const sortedAlerts = [...alerts].sort(
    (a, b) => new Date(b.event_ts).getTime() - new Date(a.event_ts).getTime(),
  )

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
      <div className="mb-3.5 flex items-center justify-between">
        <h2 className="m-0 text-[17px] font-bold text-slate-950">New alerts</h2>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">
          {alerts.length}
        </span>
      </div>

      <div className="grid gap-2.5">
        {sortedAlerts.length === 0 && (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-5 text-center">
            <strong className="block text-sm text-slate-700">No active alerts</strong>
            <span className="mt-1 block text-[13px] text-slate-500">
              Recent density, dwell, and camera health alerts will appear here.
            </span>
          </div>
        )}

        {sortedAlerts.map((alert) => (
          <article
            className="grid gap-2 rounded-lg border border-slate-200 p-3"
            key={alert.alert_id}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <strong className="block text-slate-950">{alert.title}</strong>
                <span className="block text-[13px] text-slate-500">{alert.description}</span>
              </div>

              <span
                className={`rounded-full px-2.5 py-1 text-xs font-bold ${severityClassName(alert.severity)}`}
              >
                {severityLabels[alert.severity]}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-slate-500">
              <span>{alert.camera_id}</span>
              <span>{alert.zone || 'camera'}</span>
              <span>{formatEventTime(alert.event_ts)}</span>
              {alert.trigger_value !== undefined && alert.threshold !== undefined && (
                <span>
                  {alert.trigger_value}/{alert.threshold}
                </span>
              )}
              {alert.clip_s3_uri && (
                <span className="font-bold text-blue-600" title={alert.clip_s3_uri}>
                  Clip saved
                </span>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
