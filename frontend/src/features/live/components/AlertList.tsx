import type { Alert } from '../types'

type AlertListProps = {
  alerts: Alert[]
}

const severityLabels = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

export function AlertList({ alerts }: AlertListProps) {
  return (
    <section className="panel alert-panel">
      <div className="panel-header">
        <h2>New alerts</h2>
        <button type="button">View all</button>
      </div>
      <div className="alert-list">
        {alerts.map((alert) => (
          <article className="alert-row" key={alert.alert_id}>
            <div>
              <strong>{alert.title}</strong>
              <span>{alert.description}</span>
            </div>
            <span className={`severity ${alert.severity}`}>
              {severityLabels[alert.severity]}
            </span>
          </article>
        ))}
      </div>
    </section>
  )
}
