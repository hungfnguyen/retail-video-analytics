import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Activity, Clock3, Container, Database, RefreshCw, Server, Settings2 } from 'lucide-react'
import { AppShell, type AppPage } from '../../shared/components/AppShell'
import type { ServiceHealth } from '../live/types'
import { useSystemData } from './hooks/useSystemData'

type SystemPageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

function statusClass(status: ServiceHealth['status']) {
  if (status === 'ok') return 'bg-emerald-100 text-emerald-700'
  if (status === 'warning') return 'bg-amber-100 text-amber-700'
  return 'bg-red-100 text-red-700'
}

function containerStatusClass(status: string) {
  const normalizedStatus = status.toLowerCase()
  if (normalizedStatus === 'ok') return 'rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700'
  if (normalizedStatus === 'warning') return 'rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-700'
  return 'rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-700'
}

function emptyState(message: string) {
  return (
    <div className="flex h-full min-h-32 items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-sm font-semibold text-slate-500">
      {message}
    </div>
  )
}

function formatGeneratedAt(value?: string) {
  if (!value) return 'Waiting for API'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

export function SystemPage({ activePage, onPageChange }: SystemPageProps) {
  const { data, error, refresh } = useSystemData()
  const services = data?.pipeline_health ?? []
  const throughput = data?.throughput ?? []
  const lagData = data?.lag ?? []
  const visionRuntime = data?.vision_runtime ?? []
  const containers = data?.containers ?? []
  const logs = data?.logs ?? []
  const flow = data?.flow ?? []

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      <header className="mb-4 flex items-center justify-between gap-4">
        <h1 className="m-0 text-[26px] font-bold leading-tight text-slate-950">System Monitor</h1>

        <div className="flex items-center gap-2.5">
          <button className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 font-semibold text-slate-700 shadow-sm" type="button">
            <Container size={18} />
            Local Docker
          </button>
          <button className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 font-semibold text-slate-700 shadow-sm" type="button">
            <Settings2 size={18} />
            Auto refresh 10s
          </button>
          <button
            className="flex items-center gap-2 rounded-lg border border-blue-500 bg-white px-3.5 py-2.5 font-semibold text-blue-600 shadow-sm"
            onClick={() => void refresh()}
            type="button"
          >
            <RefreshCw size={17} />
            Refresh
          </button>
          <span className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-600 shadow-sm">
            <Clock3 size={17} />
            {formatGeneratedAt(data?.generated_at)}
          </span>
        </div>
      </header>

      {error ? (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {error}
        </div>
      ) : null}

      <section className="grid grid-cols-6 gap-3">
        {services.map((service) => (
          <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]" key={service.service}>
            <div className="flex items-center gap-3">
              <Database className="text-blue-600" size={24} />
              <div>
                <strong className="block text-slate-950">{service.display_name}</strong>
                <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-bold ${statusClass(service.status)}`}>
                  {service.status.toUpperCase()}
                </span>
              </div>
            </div>
            <small className="mt-3 block text-slate-500">{service.latency_ms}ms check latency</small>
          </article>
        ))}
      </section>



      <section className="mt-3 rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="m-0 flex items-center gap-2 text-[17px] font-bold text-slate-950">
            <Activity className="text-blue-600" size={18} />
            Vision runtime
          </h2>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-700">Per camera</span>
        </div>
        {visionRuntime.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
                  <th className="py-2 pr-3">Camera</th>
                  <th className="py-2 pr-3 text-right">FPS</th>
                  <th className="py-2 pr-3 text-right">Target</th>
                  <th className="py-2 pr-3 text-right">Infer</th>
                  <th className="py-2 pr-3 text-right">Track</th>
                  <th className="py-2 pr-3 text-right">Zone</th>
                  <th className="py-2 pr-3 text-right">Queue</th>
                  <th className="py-2 pr-3 text-right">Drops</th>
                  <th className="py-2 pr-3 text-right">GPU free</th>
                  <th className="py-2 pr-3 text-right">Stable</th>
                  <th className="py-2 pr-3 text-right">Pred</th>
                  <th className="py-2 text-right">Zones</th>
                </tr>
              </thead>
              <tbody>
                {visionRuntime.map((runtime) => (
                  <tr className="border-b border-slate-100 last:border-b-0" key={runtime.camera_id}>
                    <td className="py-2 pr-3">
                      <strong className="block text-slate-900">{runtime.camera_name}</strong>
                      <span className="text-xs text-slate-500">{runtime.camera_id}</span>
                    </td>
                    <td className="py-2 pr-3 text-right font-semibold text-slate-800">{runtime.processing_fps.toFixed(1)}</td>
                    <td className="py-2 pr-3 text-right text-slate-600">{runtime.detector_fps_target.toFixed(1)}</td>
                    <td className="py-2 pr-3 text-right text-slate-600">{runtime.inference_ms}ms</td>
                    <td className="py-2 pr-3 text-right text-slate-600">{runtime.tracking_ms}ms</td>
                    <td className="py-2 pr-3 text-right text-slate-600">{runtime.zone_ms}ms</td>
                    <td className="py-2 pr-3 text-right text-slate-600">{runtime.reader_queue_size}</td>
                    <td className="py-2 pr-3 text-right text-slate-600">{runtime.dropped_frames_since_last}/{runtime.reader_drop_count}</td>
                    <td className="py-2 pr-3 text-right font-semibold text-emerald-700">{formatPercent(runtime.gpu_free_ratio)}</td>
                    <td className="py-2 pr-3 text-right text-slate-600">{runtime.stable_track_count}</td>
                    <td className="py-2 pr-3 text-right text-slate-600">{runtime.predicted_tracks_count}</td>
                    <td className="py-2 text-right text-slate-600">{runtime.zone_count_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : emptyState('No Vision runtime metadata yet')}
      </section>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Pipeline throughput</h2>
          <div className="mt-3 h-58">
            {throughput.length > 0 ? (
              <ResponsiveContainer height="100%" width="100%">
                <AreaChart data={throughput}>
                  <CartesianGrid stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="time" tickLine={false} />
                  <YAxis tickLine={false} width={46} />
                  <Tooltip />
                  <Area dataKey="events" fill="#bfdbfe" name="Active events" stroke="#2563eb" strokeWidth={2} />
                  <Line dataKey="frames" dot={false} name="Processed frames / sec" stroke="#059669" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : emptyState('No live throughput samples yet')}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Backlog and lag</h2>
          <div className="mt-3 h-58">
            {lagData.length > 0 ? (
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={lagData}>
                  <CartesianGrid stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="time" tickLine={false} />
                  <YAxis tickLine={false} width={54} />
                  <Tooltip />
                  <Bar dataKey="backlog" fill="#3b82f6" name="Reader backlog" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="lag" fill="#22c55e" name="Media lag" radius={[4, 4, 0, 0]} />
                  <Line dataKey="api" name="API latency" stroke="#f97316" strokeWidth={2} />
                </BarChart>
              </ResponsiveContainer>
            ) : emptyState('No lag samples yet')}
          </div>
        </section>
      </div>

      <div className="mt-3 grid grid-cols-[0.9fr_1.1fr] gap-3">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Container status</h2>
          <table className="mt-3 w-full border-collapse text-sm">
            <tbody>
              {containers.map((container) => {
                return (
                  <tr className="border-t border-slate-200" key={container.name}>
                    <td className="py-2 font-semibold text-slate-700">{container.name}</td>
                    <td>
                      <span className={containerStatusClass(container.status)}>
                        {container.status}
                      </span>
                    </td>
                    <td className="text-right text-slate-600">{container.cpu}</td>
                    <td className="text-right text-slate-600">{container.memory}</td>
                    <td className="text-right text-slate-600">{container.uptime}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {containers.length === 0 ? emptyState('No service status available') : null}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Recent logs</h2>
          <table className="mt-3 w-full border-collapse text-sm">
            <tbody>
              {logs.map((log, index) => (
                <tr className="border-t border-slate-200" key={`${log.service}-${index}`}>
                  <td className="py-2 text-slate-600">{log.time || '-'}</td>
                  <td><span className={log.level === 'WARN' ? 'rounded bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-700' : log.level === 'ERROR' ? 'rounded bg-red-100 px-2 py-0.5 text-xs font-bold text-red-700' : 'rounded bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700'}>{log.level}</span></td>
                  <td className="font-semibold text-slate-700">{log.service}</td>
                  <td className="text-slate-600">{log.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {logs.length === 0 ? emptyState('No recent log entries found') : null}
        </section>
      </div>

      <section className="mt-3 rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Pipeline flow</h2>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-700">Topology</span>
        </div>

        <div className="grid grid-cols-[repeat(6,1fr)] gap-3">
          {flow.map((step) => (
            <article className="rounded-lg border border-slate-200 bg-slate-50 p-3" key={step.name}>
              <Server className="mb-2 text-blue-600" size={20} />
              <strong className="block text-sm text-slate-800">{step.name}</strong>
              <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-bold ${statusClass(step.status as ServiceHealth['status'])}`}>
                {step.status.toUpperCase()}
              </span>
            </article>
          ))}
        </div>
        {flow.length === 0 ? emptyState('No pipeline topology available') : null}
      </section>
    </AppShell>
  )
}
