import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Activity, Camera, Clock, TrendingUp, Users } from 'lucide-react'
import type { AnalyticsDashboardData, AnalyticsKpi, HeatmapCell } from '../types'

const toneClasses = {
  blue: {
    icon: 'bg-blue-50 text-blue-700 ring-blue-100',
    value: 'text-blue-700',
  },
  emerald: {
    icon: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
    value: 'text-emerald-700',
  },
  amber: {
    icon: 'bg-amber-50 text-amber-700 ring-amber-100',
    value: 'text-amber-700',
  },
  violet: {
    icon: 'bg-violet-50 text-violet-700 ring-violet-100',
    value: 'text-violet-700',
  },
}

const kpiIcons = [Users, TrendingUp, Camera, Clock]

function formatNumber(value: number) {
  return value.toLocaleString()
}

function formatDuration(seconds: number) {
  if (seconds <= 0) return '0s'
  const minutes = Math.floor(seconds / 60)
  const remaining = Math.round(seconds % 60)
  return minutes > 0 ? `${minutes}m ${remaining.toString().padStart(2, '0')}s` : `${remaining}s`
}

function KpiCard({ kpi, index }: { kpi: AnalyticsKpi; index: number }) {
  const Icon = kpiIcons[index] ?? Activity
  const classes = toneClasses[kpi.tone]

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
      <div className="flex items-center gap-3">
        <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-lg ring-1 ${classes.icon}`}>
          <Icon size={23} />
        </span>

        <div className="min-w-0">
          <span className="block text-sm font-semibold text-slate-500">{kpi.label}</span>
          <strong className={`mt-1 block truncate text-[28px] leading-none ${classes.value}`}>{kpi.value}</strong>
          <small className="mt-1.5 block truncate text-xs font-semibold text-slate-500">{kpi.meta}</small>
        </div>
      </div>
    </article>
  )
}

function heatmapValue(cells: HeatmapCell[], row: number, col: number) {
  return cells.find((cell) => cell.row === row && cell.col === col)?.value ?? 0
}

function heatmapColor(value: number, max: number) {
  if (!value || !max) return 'rgba(226, 232, 240, 0.72)'
  const intensity = value / max
  if (intensity > 0.8) return '#ef4444'
  if (intensity > 0.55) return '#f59e0b'
  if (intensity > 0.32) return '#22c55e'
  return '#bfdbfe'
}

function DensityHeatmap({ cells }: { cells: HeatmapCell[] }) {
  const max = Math.max(...cells.map((cell) => cell.value), 0)
  const rows = Array.from({ length: 6 }, (_, index) => index)
  const cols = Array.from({ length: 8 }, (_, index) => index)

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="m-0 text-[17px] font-bold text-slate-950">Frame density</h2>
        <span className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">bbox center</span>
      </div>

      <div className="grid aspect-[4/3] grid-cols-8 gap-1 rounded-lg bg-slate-950 p-2">
        {rows.flatMap((row) =>
          cols.map((col) => {
            const value = heatmapValue(cells, row, col)
            return (
              <span
                className="grid place-items-center rounded-[5px] text-[11px] font-bold text-slate-950"
                key={`${row}-${col}`}
                style={{ backgroundColor: heatmapColor(value, max) }}
                title={`${formatNumber(value)} detections`}
              >
                {value > 0 ? formatNumber(value) : ''}
              </span>
            )
          }),
        )}
      </div>
    </section>
  )
}

export function AnalyticsPanels({ data }: { data: AnalyticsDashboardData }) {
  return (
    <>
      <section className="grid grid-cols-4 gap-3">
        {data.kpis.map((kpi, index) => (
          <KpiCard index={index} key={kpi.label} kpi={kpi} />
        ))}
      </section>

      <div className="mt-3 grid grid-cols-[1.18fr_0.82fr] gap-3">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="m-0 text-[17px] font-bold text-slate-950">Hourly detections</h2>
            <span className="rounded-md bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">{data.range_label}</span>
          </div>

          <div className="h-[292px]">
            <ResponsiveContainer height="100%" width="100%">
              <ComposedChart data={data.hourly_traffic}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="hour" tickLine={false} />
                <YAxis tickLine={false} width={44} />
                <Tooltip formatter={(value) => formatNumber(Number(value))} />
                <Bar dataKey="detections" fill="#2563eb" name="Detections" radius={[4, 4, 0, 0]} />
                <Line dataKey="average" dot={false} name="Per-day avg" stroke="#059669" strokeDasharray="4 4" strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="m-0 text-[17px] font-bold text-slate-950">Camera share</h2>
            <span className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">Silver rows</span>
          </div>

          <div className="h-[292px]">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={data.camera_comparison} layout="vertical">
                <CartesianGrid stroke="#e2e8f0" horizontal={false} />
                <XAxis tickLine={false} type="number" />
                <YAxis dataKey="camera_id" tickLine={false} type="category" width={78} />
                <Tooltip formatter={(value) => formatNumber(Number(value))} />
                <Bar dataKey="detections" radius={[0, 5, 5, 0]}>
                  {data.camera_comparison.map((item, index) => (
                    <Cell fill={index === 0 ? '#0f766e' : index === 1 ? '#14b8a6' : '#5eead4'} key={item.camera_id} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <div className="mt-3 grid grid-cols-[0.92fr_0.82fr_1.12fr] gap-3">
        <DensityHeatmap cells={data.heatmap} />

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="m-0 text-[17px] font-bold text-slate-950">Dwell bands</h2>
            <span className="rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">Gold tracks</span>
          </div>

          <div className="grid gap-3">
            {data.dwell_bands.map((band) => (
              <div className="grid grid-cols-[76px_1fr_46px] items-center gap-3 text-sm" key={band.label}>
                <span className="font-semibold text-slate-600">{band.label}</span>
                <span className="h-4 rounded-full bg-slate-100">
                  <span className="block h-4 rounded-full bg-emerald-500" style={{ width: `${Math.min(100, band.value)}%` }} />
                </span>
                <span className="text-right font-semibold text-slate-600">{band.value}%</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Daily summary</h2>

          <table className="mt-4 w-full border-collapse text-sm">
            <thead>
              <tr className="border border-slate-200 bg-slate-50 text-slate-600">
                <th className="px-3 py-2 text-left">Date</th>
                <th className="px-3 py-2 text-right">Detections</th>
                <th className="px-3 py-2 text-right">Peak</th>
                <th className="px-3 py-2 text-right">Avg dwell</th>
              </tr>
            </thead>
            <tbody>
              {data.daily_summary.map((row) => (
                <tr className="border border-slate-200" key={row.date}>
                  <td className="px-3 py-2 font-semibold text-blue-700">{row.date}</td>
                  <td className="px-3 py-2 text-right text-slate-700">{formatNumber(row.detections)}</td>
                  <td className="px-3 py-2 text-right text-slate-700">{row.peak}</td>
                  <td className="px-3 py-2 text-right text-slate-700">{formatDuration(row.avg_dwell_sec)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </>
  )
}
