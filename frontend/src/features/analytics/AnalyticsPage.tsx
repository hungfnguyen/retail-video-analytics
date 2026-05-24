import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { CalendarDays, Camera, Download, RefreshCw, Store, TrendingUp, Users } from 'lucide-react'
import { AppShell, type AppPage } from '../../shared/components/AppShell'

type AnalyticsPageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

const hourlyTraffic = [
  { hour: '00:00', detections: 210, average: 95 },
  { hour: '02:00', detections: 120, average: 60 },
  { hour: '04:00', detections: 150, average: 80 },
  { hour: '06:00', detections: 560, average: 420 },
  { hour: '08:00', detections: 740, average: 550 },
  { hour: '10:00', detections: 670, average: 540 },
  { hour: '12:00', detections: 650, average: 520 },
  { hour: '14:00', detections: 920, average: 710 },
  { hour: '16:00', detections: 1320, average: 1040 },
  { hour: '18:00', detections: 1342, average: 1168 },
  { hour: '20:00', detections: 670, average: 520 },
  { hour: '22:00', detections: 260, average: 180 },
]

const cameraComparison = [
  { camera: 'Cam 01', zone: 'Entrance', detections: 5230, share: '41.9%' },
  { camera: 'Cam 02', zone: 'Side Door', detections: 3870, share: '31.0%' },
  { camera: 'Cam 03', zone: 'Checkout', detections: 3380, share: '27.1%' },
]

const heatmapRows = [
  { zone: 'A1 - Entrance', values: [120, 340, 980, 1280, 1520, 990] },
  { zone: 'A2 - Main Aisle', values: [80, 220, 760, 1110, 1260, 780] },
  { zone: 'B1 - Promotion', values: [60, 160, 540, 920, 1180, 640] },
  { zone: 'B2 - Fitting Room', values: [40, 110, 320, 610, 820, 430] },
  { zone: 'C1 - Checkout', values: [100, 260, 880, 1210, 1500, 970] },
  { zone: 'C2 - Exit', values: [70, 150, 460, 740, 940, 560] },
]

const dwellBands = [
  { label: '< 30s', value: 18.6 },
  { label: '30s - 1m', value: 19.7 },
  { label: '1m - 2m', value: 21.4 },
  { label: '2m - 5m', value: 24.3 },
  { label: '5m - 10m', value: 10.1 },
  { label: '> 10m', value: 5.9 },
]

const dailySummary = [
  ['2026-05-16', '12,480', '18:00 (1,342)', '24.8'],
  ['2026-05-15', '11,516', '17:00 (1,201)', '24.6'],
  ['2026-05-14', '10,923', '17:00 (1,132)', '24.7'],
  ['2026-05-13', '10,102', '16:00 (1,048)', '24.5'],
  ['2026-05-12', '9,876', '18:00 (1,021)', '24.4'],
  ['2026-05-11', '9,432', '17:00 (980)', '24.6'],
  ['2026-05-10', '8,945', '16:00 (912)', '24.3'],
]

const kpis = [
  {
    label: 'Total detections',
    value: '12,480',
    meta: 'Yesterday: 11,516',
    icon: Users,
    tone: 'blue',
  },
  {
    label: 'Peak hour',
    value: '18:00',
    meta: 'Detections: 1,342',
    icon: CalendarDays,
    tone: 'emerald',
  },
  {
    label: 'Busiest camera',
    value: 'Cam 01',
    meta: '5,230 detections (41.9%)',
    icon: Camera,
    tone: 'violet',
  },
  {
    label: 'Vs yesterday',
    value: '+8.4%',
    meta: '+964 detections',
    icon: TrendingUp,
    tone: 'emerald',
  },
]

const timeBuckets = ['00-04', '04-08', '08-12', '12-16', '16-20', '20-24']

function heatCellClass(value: number) {
  if (value >= 1400) return 'bg-red-400 text-slate-950'
  if (value >= 1000) return 'bg-amber-300 text-slate-950'
  if (value >= 600) return 'bg-yellow-200 text-slate-950'
  if (value >= 250) return 'bg-green-200 text-slate-950'
  return 'bg-emerald-100 text-slate-700'
}

export function AnalyticsPage({ activePage, onPageChange }: AnalyticsPageProps) {
  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      <header className="mb-4 flex items-center justify-between gap-4">
        <h1 className="m-0 text-[26px] font-bold leading-tight text-slate-950">Traffic Analytics</h1>

        <div className="flex items-center gap-2.5">
          <button className="flex min-w-44 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 font-semibold text-slate-700 shadow-sm" type="button">
            <Store size={18} />
            Store 001
          </button>
          <button className="flex min-w-48 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 font-semibold text-slate-700 shadow-sm" type="button">
            <Camera size={18} />
            All cameras
          </button>
          <button className="flex min-w-44 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 font-semibold text-slate-700 shadow-sm" type="button">
            <CalendarDays size={18} />
            Today
          </button>
          <button className="flex items-center gap-2 rounded-lg border border-blue-500 bg-white px-3.5 py-2.5 font-semibold text-blue-600 shadow-sm" type="button">
            <Download size={17} />
            Export report
          </button>
          <button className="grid h-10 w-10 place-items-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm" type="button">
            <RefreshCw size={17} />
          </button>
        </div>
      </header>

      <section className="grid grid-cols-4 gap-3">
        {kpis.map((kpi) => {
          const Icon = kpi.icon
          const iconClass = kpi.tone === 'violet' ? 'bg-violet-100 text-violet-700' : kpi.tone === 'emerald' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'
          const valueClass = kpi.tone === 'violet' ? 'text-violet-700' : kpi.tone === 'emerald' ? 'text-emerald-700' : 'text-blue-600'

          return (
            <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-[0_12px_34px_rgba(15,23,42,0.06)]" key={kpi.label}>
              <div className="flex items-center gap-4">
                <span className={`grid h-13 w-13 place-items-center rounded-full ${iconClass}`}>
                  <Icon size={25} />
                </span>
                <div>
                  <span className="block text-sm font-semibold text-slate-600">{kpi.label}</span>
                  <strong className={`mt-1 block text-[30px] leading-none ${valueClass}`}>{kpi.value}</strong>
                  <small className="mt-2 block text-sm font-medium text-slate-500">{kpi.meta}</small>
                </div>
              </div>
            </article>
          )
        })}
      </section>

      <div className="mt-3 grid grid-cols-[1.25fr_0.85fr] gap-3">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="m-0 text-[17px] font-bold text-slate-950">Hourly traffic</h2>
            <span className="rounded-md border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-600">Hourly</span>
          </div>

          <div className="h-71">
            <ResponsiveContainer height="100%" width="100%">
              <ComposedChart data={hourlyTraffic}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="hour" tickLine={false} />
                <YAxis tickLine={false} width={42} />
                <Tooltip />
                <Legend />
                <Bar dataKey="detections" fill="#60a5fa" name="Detections" radius={[4, 4, 0, 0]} />
                <Line dataKey="average" dot={false} name="7-day average" stroke="#059669" strokeDasharray="4 4" strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="m-0 text-[17px] font-bold text-slate-950">Camera comparison</h2>
            <span className="rounded-md border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-600">By detections</span>
          </div>

          <div className="h-71">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={cameraComparison} layout="vertical">
                <CartesianGrid stroke="#e2e8f0" horizontal={false} />
                <XAxis tickLine={false} type="number" />
                <YAxis dataKey="camera" tickLine={false} type="category" width={74} />
                <Tooltip />
                <Bar dataKey="detections" fill="#2563eb" radius={[0, 5, 5, 0]}>
                  {cameraComparison.map((item, index) => (
                    <Cell fill={index === 0 ? '#2563eb' : index === 1 ? '#3b82f6' : '#60a5fa'} key={item.camera} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <div className="mt-3 grid grid-cols-[0.98fr_0.78fr_1fr] gap-3">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Historical heatmap</h2>

          <div className="mt-4 grid grid-cols-[120px_repeat(6,1fr)] gap-1 text-center text-xs font-semibold">
            <span className="text-left text-slate-600">Zone</span>
            {timeBuckets.map((bucket) => (
              <span className="text-slate-600" key={bucket}>{bucket}</span>
            ))}
            {heatmapRows.map((row) => (
              <>
                <span className="py-2 text-left text-slate-700" key={`${row.zone}-label`}>{row.zone}</span>
                {row.values.map((value, index) => (
                  <span className={`rounded-sm py-2 ${heatCellClass(value)}`} key={`${row.zone}-${index}`}>{value.toLocaleString()}</span>
                ))}
              </>
            ))}
          </div>

          <div className="mt-4 flex items-center gap-3 text-xs font-semibold text-slate-500">
            <span>Low</span>
            <span className="h-2 flex-1 rounded-full bg-gradient-to-r from-emerald-300 via-yellow-200 to-red-400" />
            <span>High</span>
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="m-0 text-[17px] font-bold text-slate-950">Dwell time</h2>
            <span className="text-sm font-semibold text-slate-500">Avg: 3m 12s</span>
          </div>

          <div className="grid gap-3">
            {dwellBands.map((band) => (
              <div className="grid grid-cols-[72px_1fr_42px] items-center gap-3 text-sm" key={band.label}>
                <span className="font-semibold text-slate-600">{band.label}</span>
                <span className="h-4 rounded-full bg-slate-100">
                  <span className="block h-4 rounded-full bg-blue-500" style={{ width: `${band.value * 2.3}%` }} />
                </span>
                <span className="font-semibold text-slate-600">{band.value}%</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
          <h2 className="m-0 text-[17px] font-bold text-slate-950">Daily summary</h2>

          <table className="mt-4 w-full border-collapse text-sm">
            <thead>
              <tr className="border border-slate-200 bg-slate-50 text-slate-600">
                <th className="px-3 py-2 text-left">Date</th>
                <th className="px-3 py-2 text-right">Detections</th>
                <th className="px-3 py-2 text-right">Peak</th>
                <th className="px-3 py-2 text-right">Avg FPS</th>
              </tr>
            </thead>
            <tbody>
              {dailySummary.map(([date, detections, peak, fps]) => (
                <tr className="border border-slate-200" key={date}>
                  <td className="px-3 py-2 font-semibold text-blue-600">{date}</td>
                  <td className="px-3 py-2 text-right text-slate-700">{detections}</td>
                  <td className="px-3 py-2 text-right text-blue-600">{peak}</td>
                  <td className="px-3 py-2 text-right text-slate-700">{fps}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </AppShell>
  )
}
