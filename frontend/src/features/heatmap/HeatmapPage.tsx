import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { AppShell, type AppPage } from '../../shared/components/AppShell'
import { RealtimeHeatmap } from './components/RealtimeHeatmap'
import { TrafficHeatmap } from './components/TrafficHeatmap'
import { useHeatmapData } from './hooks/useHeatmapData'

type HeatmapPageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

type HeatmapTab = 'realtime' | 'traffic'

const CAMERA_IDS = ['cam_01', 'cam_02']
const DAY_OPTIONS = [1, 7, 14, 30]

function TrafficRefreshButton({ cameraId, days }: { cameraId: string; days: number }) {
  const { refresh, loading } = useHeatmapData(cameraId, days)
  return (
    <button
      className="grid h-10 w-10 place-items-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-blue-300 hover:text-blue-700 disabled:opacity-50"
      disabled={loading}
      onClick={() => void refresh()}
      title="Refresh heatmap"
      type="button"
    >
      <RefreshCw className={loading ? 'animate-spin' : ''} size={17} />
    </button>
  )
}

export function HeatmapPage({ activePage, onPageChange }: HeatmapPageProps) {
  const [tab, setTab] = useState<HeatmapTab>('realtime')
  const [cameraId, setCameraId] = useState('cam_01')
  const [days, setDays] = useState(7)

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      <header className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="m-0 text-[26px] font-bold leading-tight text-slate-950">Presence Heatmap</h1>
          <p className="m-0 mt-1 text-sm font-semibold text-slate-500">
            Camera-view traffic density — realtime Redis data and historical Silver layer
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Tab switcher */}
          <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
            {(['realtime', 'traffic'] as HeatmapTab[]).map((t) => (
              <button
                className={`rounded-md px-3 py-2 text-sm font-bold transition ${
                  tab === t ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-slate-100'
                }`}
                key={t}
                onClick={() => setTab(t)}
                type="button"
              >
                {t === 'realtime' ? 'Realtime' : 'Traffic'}
              </button>
            ))}
          </div>

          {/* Camera selector */}
          <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
            {CAMERA_IDS.map((id) => (
              <button
                className={`rounded-md px-3 py-2 text-sm font-bold transition ${
                  cameraId === id ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-slate-100'
                }`}
                key={id}
                onClick={() => setCameraId(id)}
                type="button"
              >
                {id}
              </button>
            ))}
          </div>

          {/* Days selector — traffic tab only */}
          {tab === 'traffic' && (
            <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
              {DAY_OPTIONS.map((d) => (
                <button
                  className={`rounded-md px-3 py-2 text-sm font-bold transition ${
                    days === d ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                  key={d}
                  onClick={() => setDays(d)}
                  type="button"
                >
                  {d}d
                </button>
              ))}
            </div>
          )}

          {/* Refresh — traffic tab only */}
          {tab === 'traffic' && <TrafficRefreshButton cameraId={cameraId} days={days} />}
        </div>
      </header>

      {tab === 'realtime' ? (
        <RealtimeHeatmap cameraId={cameraId} />
      ) : (
        <TrafficHeatmap cameraId={cameraId} days={days} />
      )}
    </AppShell>
  )
}
