import type { ServiceHealth } from '../types'

type PipelineHealthProps = {
  services: ServiceHealth[]
}

export function PipelineHealth({ services }: PipelineHealthProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_18px_45px_rgba(15,23,42,0.08)]">
      <div className="mb-3.5 flex items-center justify-between">
        <h2 className="m-0 text-[17px] font-bold text-slate-950">Pipeline health</h2>
        <button className="border-0 bg-transparent font-bold text-blue-600" type="button">Details</button>
      </div>

      <div className="grid gap-2.5">
        {services.map((service) => (
          <article
            className="grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded-lg border border-slate-200 p-3"
            key={service.service}
          >
            <div>
              <strong className="block text-slate-950">{service.display_name}</strong>
              <span className="block text-[13px] text-slate-500">{service.role}</span>
            </div>

            <span
              className={
                service.status === 'ok'
                  ? 'rounded-full bg-green-100 px-2.5 py-1 text-xs font-bold text-green-700'
                  : service.status === 'warning'
                    ? 'rounded-full bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-700'
                    : 'rounded-full bg-red-100 px-2.5 py-1 text-xs font-bold text-red-700'
              }
            >
              {service.status.toUpperCase()}
            </span>

            <small className="text-[13px] text-slate-500">{service.latency_ms}ms</small>
          </article>
        ))}
      </div>
    </section>
  )
}
