import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { AppShell } from '../../shared/components/AppShell'
import { AlertList } from './components/AlertList'
import { LiveMetricCards } from './components/LiveMetricCards'
import { TrafficChart } from './components/TrafficChart'
import { VideoPanel } from './components/VideoPanel'
import { ZoneHeatmap } from './components/ZoneHeatmap'
import { ZoneRuntimePanel } from './components/ZoneRuntimePanel'
import { useLiveData } from './hooks/useLiveData'
import type { AppPage } from '../../shared/components/AppShell'

type LivePageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

export function LivePage({ activePage, onPageChange }: LivePageProps) {
  const { data, error, switchCamera } = useLiveData()
  const [cameraMenuOpen, setCameraMenuOpen] = useState(false)

  if (error) {
    return <div className="grid min-h-screen place-items-center">{error}</div>
  }

  if (!data) {
    return <div className="grid min-h-screen place-items-center">Loading live dashboard...</div>
  }

  const selectedCamera = data.cameras.find(
    (camera) => camera.camera_id === data.selected_camera_id,
  )
  const statusBadge = selectedCamera?.status === 'online'
    ? { label: 'Running', className: 'border-emerald-200 bg-emerald-50 text-emerald-700' }
    : { label: 'Warning', className: 'border-amber-200 bg-amber-50 text-amber-700' }

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      {/* Page header */}
      <header className="mb-5 flex items-center justify-between">
        <h1 className="m-0 text-[26px] font-bold leading-tight text-slate-950">Live Store Monitor</h1>

        <div className="flex items-center gap-3">
          <div className="relative">
            <button
              className="flex min-w-55 items-center justify-between gap-8 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-slate-950 shadow-sm"
              onClick={() => setCameraMenuOpen((prev) => !prev)}
              onBlur={() => setTimeout(() => setCameraMenuOpen(false), 150)}
              type="button"
            >
              {selectedCamera?.name ?? data.selected_camera_id}
              <ChevronDown size={16} />
            </button>

            {cameraMenuOpen && (
              <div className="absolute right-0 z-50 mt-1 w-full rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
                {data.cameras.map((camera) => (
                  <button
                    className={`w-full px-3.5 py-2 text-left text-sm hover:bg-blue-50 ${
                      camera.camera_id === data.selected_camera_id
                        ? 'font-bold text-blue-600'
                        : 'text-slate-700'
                    }`}
                    key={camera.camera_id}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      switchCamera(camera.camera_id)
                      setCameraMenuOpen(false)
                    }}
                    type="button"
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${
                          camera.status === 'online' ? 'bg-emerald-500' : 'bg-amber-500'
                        }`}
                      />
                      {camera.name ?? camera.camera_id}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <span
            className={`rounded-lg border px-4.5 py-2.5 font-bold ${statusBadge.className}`}
          >
            {statusBadge.label}
          </span>
        </div>
      </header>

      {/* Primary live monitoring area */}
      <div className="grid gap-5">
        <LiveMetricCards stats={data.stats} />
        <VideoPanel frame={data.frame} />
      </div>

      <div className="mt-5 grid grid-cols-[1.35fr_0.75fr] gap-5">
        <ZoneRuntimePanel
          lineCrossings={data.frame.line_crossings}
          zoneCounts={data.frame.zone_counts}
        />
        <AlertList alerts={data.alerts} />
      </div>

      {/* Supporting live analytics */}
      <div className="mt-5 grid grid-cols-[1.25fr_0.85fr] gap-5">
        <TrafficChart
          summary={data.traffic_summary}
          traffic={data.traffic}
        />
        <ZoneHeatmap cells={data.zone_heatmap} />
      </div>
    </AppShell>
  )
}
