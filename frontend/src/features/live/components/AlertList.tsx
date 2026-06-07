import type { Alert } from '../types'

type AlertListProps = {
  alerts: Alert[]
}

const severityLabels = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

function formatRelativeTime(iso: string): string {
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  return `${Math.floor(min / 60)}h ago`
}

export function AlertList({ alerts }: AlertListProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
      <div className="mb-3.5 flex items-center justify-between">
        <h2 className="m-0 text-[17px] font-bold text-slate-950">New alerts</h2>
        <button className="border-0 bg-transparent font-bold text-blue-600" type="button">View all</button>
      </div>

      {alerts.length === 0 ? (
        <div className="grid min-h-24 place-items-center rounded-lg border border-dashed border-slate-200 text-sm text-slate-400">
          No active alerts
        </div>
      ) : (
        <div className="grid gap-2.5">
          {alerts.map((alert) => (
            <article
              className="grid grid-cols-[1fr_auto] items-start gap-3 rounded-lg border border-slate-200 p-3"
              key={alert.alert_id}
            >
              <div className="min-w-0">
                <strong className="block text-slate-950">{alert.title}</strong>
                <span className="block text-[13px] text-slate-500">{alert.description}</span>
                <span className="block text-[12px] text-slate-400">{formatRelativeTime(alert.event_ts)}</span>
              </div>

              <span
                className={
                  alert.severity === 'high'
                    ? 'rounded-full bg-red-100 px-2.5 py-1 text-xs font-bold text-red-600'
                    : alert.severity === 'medium'
                      ? 'rounded-full bg-orange-100 px-2.5 py-1 text-xs font-bold text-orange-700'
                      : 'rounded-full bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-700'
                }
              >
                {severityLabels[alert.severity]}
              </span>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
