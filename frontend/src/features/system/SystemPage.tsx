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
import { Clock3, Container, Database, RefreshCw, Server, Settings2 } from 'lucide-react'
import { useLiveData } from '../live/hooks/useLiveData'
import { AppShell, type AppPage } from '../../shared/components/AppShell'
import type { ServiceHealth } from '../live/types'

type SystemPageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

const throughput = [
  { time: '15:31', events: 16800, frames: 210 },
  { time: '15:33', events: 20500, frames: 250 },
  { time: '15:35', events: 21400, frames: 280 },
  { time: '15:37', events: 19800, frames: 235 },
  { time: '15:39', events: 12600, frames: 215 },
  { time: '15:41', events: 18742, frames: 362 },
]

const lagData = [
  { time: '15:31', backlog: 150000, lag: 116000, api: 150 },
  { time: '15:33', backlog: 210000, lag: 150000, api: 172 },
  { time: '15:35', backlog: 115000, lag: 86000, api: 205 },
  { time: '15:37', backlog: 94000, lag: 72000, api: 148 },
  { time: '15:39', backlog: 121000, lag: 88000, api: 181 },
  { time: '15:41', backlog: 145000, lag: 103000, api: 146 },
]

const containers = [
  ['vision-edge', 'Running', '18.7%', '512Mi / 2Gi', '4d 02h 13m'],
  ['pulsar', 'Running', '12.1%', '1.2Gi / 4Gi', '4d 02h 13m'],
  ['flink-jobmanager', 'Running', '14.5%', '1.1Gi / 4Gi', '4d 02h 10m'],
  ['flink-taskmanager', 'Running', '32.8%', '2.6Gi / 8Gi', '4d 02h 10m'],
  ['minio', 'Running', '16.3%', '768Mi / 4Gi', '4d 02h 09m'],
  ['fastapi', 'Running', '9.6%', '256Mi / 1Gi', '4d 02h 07m'],
]

const logs = [
  ['15:41:05', 'INFO', 'vision-edge', '[track] emitted 23 objects, 362 frames processed'],
  ['15:41:04', 'INFO', 'pulsar', 'Published 18,742 messages to topic rva.events'],
  ['15:41:03', 'INFO', 'flink-jobmanager', 'Checkpoint completed in 1.18s'],
  ['15:41:02', 'INFO', 'flink-taskmanager', 'Processed 18,512 records'],
  ['15:41:01', 'WARN', 'minio', 'S3 backend response 210ms for PutObject'],
  ['15:41:00', 'INFO', 'fastapi', 'GET /api/v1/live/stats 200 12ms'],
]

const flow = ['Vision Edge', 'Apache Pulsar', 'Apache Flink', 'Iceberg / Redis', 'FastAPI BFF', 'UI Web SPA']

function statusClass(status: ServiceHealth['status']) {
  if (status === 'ok') return 'bg-emerald-100 text-emerald-700'
  if (status === 'warning') return 'bg-amber-100 text-amber-700'
  return 'bg-red-100 text-red-700'
}

function serviceCards(services: ServiceHealth[]) {
  if (services.length > 0) return services
  return [
    { service: 'pulsar', display_name: 'Pulsar', role: 'Event broker', status: 'warning', latency_ms: 0, last_check_ts: '' },
    { service: 'flink', display_name: 'Flink', role: 'Stream processing', status: 'warning', latency_ms: 0, last_check_ts: '' },
    { service: 'minio', display_name: 'MinIO', role: 'Object storage', status: 'warning', latency_ms: 0, last_check_ts: '' },
    { service: 'trino', display_name: 'Trino', role: 'SQL analytics', status: 'warning', latency_ms: 0, last_check_ts: '' },
    { service: 'redis', display_name: 'Redis', role: 'Realtime state', status: 'warning', latency_ms: 0, last_check_ts: '' },
    { service: 'fastapi', display_name: 'FastAPI', role: 'Backend gateway', status: 'warning', latency_ms: 0, last_check_ts: '' },
  ] satisfies ServiceHealth[]
}

export function SystemPage({ activePage, onPageChange }: SystemPageProps) {
  const { data } = useLiveData()
  const services = serviceCards(data?.pipeline_health ?? [])

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
          <button className="flex items-center gap-2 rounded-lg border border-blue-500 bg-white px-3.5 py-2.5 font-semibold text-blue-600 shadow-sm" type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
          <span className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-600 shadow-sm">
            <Clock3 size={17} />
            2026-05-24 19:41:07
          </span>
        </div>
      </header>

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

      <div className="mt-3 grid grid-cols-2 gap-3">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Pipeline throughput</h2>
          <div className="mt-3 h-58">
            <ResponsiveContainer height="100%" width="100%">
              <AreaChart data={throughput}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="time" tickLine={false} />
                <YAxis tickLine={false} width={46} />
                <Tooltip />
                <Area dataKey="events" fill="#bfdbfe" name="Events / sec" stroke="#2563eb" strokeWidth={2} />
                <Line dataKey="frames" dot={false} name="Processed frames / sec" stroke="#059669" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Backlog and lag</h2>
          <div className="mt-3 h-58">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={lagData}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="time" tickLine={false} />
                <YAxis tickLine={false} width={54} />
                <Tooltip />
                <Bar dataKey="backlog" fill="#3b82f6" name="Pulsar backlog" radius={[4, 4, 0, 0]} />
                <Bar dataKey="lag" fill="#22c55e" name="Flink lag" radius={[4, 4, 0, 0]} />
                <Line dataKey="api" name="API p95 latency" stroke="#f97316" strokeWidth={2} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <div className="mt-3 grid grid-cols-[0.9fr_1.1fr] gap-3">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Container status</h2>
          <table className="mt-3 w-full border-collapse text-sm">
            <tbody>
              {containers.map(([name, status, cpu, memory, uptime]) => (
                <tr className="border-t border-slate-200" key={name}>
                  <td className="py-2 font-semibold text-slate-700">{name}</td>
                  <td><span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700">{status}</span></td>
                  <td className="text-right text-slate-600">{cpu}</td>
                  <td className="text-right text-slate-600">{memory}</td>
                  <td className="text-right text-slate-600">{uptime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Recent logs</h2>
          <table className="mt-3 w-full border-collapse text-sm">
            <tbody>
              {logs.map(([time, level, service, message]) => (
                <tr className="border-t border-slate-200" key={`${time}-${service}`}>
                  <td className="py-2 text-slate-600">{time}</td>
                  <td><span className={level === 'WARN' ? 'rounded bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-700' : 'rounded bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700'}>{level}</span></td>
                  <td className="font-semibold text-slate-700">{service}</td>
                  <td className="text-slate-600">{message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section className="mt-3 rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Pipeline flow</h2>
          <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-700">Stable</span>
        </div>

        <div className="grid grid-cols-[repeat(6,1fr)] gap-3">
          {flow.map((step) => (
            <article className="rounded-lg border border-slate-200 bg-slate-50 p-3" key={step}>
              <Server className="mb-2 text-blue-600" size={20} />
              <strong className="block text-sm text-slate-800">{step}</strong>
              <span className="mt-1 block text-xs font-semibold text-slate-500">Operational</span>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  )
}
