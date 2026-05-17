import type { ServiceHealth } from '../types'

type PipelineHealthProps = {
  services: ServiceHealth[]
}

export function PipelineHealth({ services }: PipelineHealthProps) {
  return (
    <section className="panel pipeline-panel">
      <div className="panel-header">
        <h2>Pipeline health</h2>
        <button type="button">Details</button>
      </div>
      <div className="service-list">
        {services.map((service) => (
          <article className="service-row" key={service.service}>
            <div>
              <strong>{service.display_name}</strong>
              <span>{service.role}</span>
            </div>
            <span className={`status-pill ${service.status}`}>
              {service.status.toUpperCase()}
            </span>
            <small>{service.latency_ms}ms</small>
          </article>
        ))}
      </div>
    </section>
  )
}
