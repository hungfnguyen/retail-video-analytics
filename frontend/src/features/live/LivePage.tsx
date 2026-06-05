import { AlertTriangle, ChevronDown, Video } from 'lucide-react'
import { useState } from 'react'
import { AppShell } from '../../shared/components/AppShell'
import { AlertList } from './components/AlertList'
import { LiveMetricCards } from './components/LiveMetricCards'
import { TrafficChart } from './components/TrafficChart'
import { VideoPanel } from './components/VideoPanel'
import { ZoneHeatmap } from './components/ZoneHeatmap'
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
  const highAlertCameraIds = new Set(
    data.alerts.filter((alert) => alert.severity === 'high').map((alert) => alert.camera_id),
  )
  const activeAlertCameraIds = new Set(
    data.alerts.filter((alert) => alert.status === 'new').map((alert) => alert.camera_id),
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

        <section className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3" aria-label="Camera overview">
          {data.cameras.map((camera) => {
            const isSelected = camera.camera_id === data.selected_camera_id
            const hasHighAlert = highAlertCameraIds.has(camera.camera_id)
            const hasActiveAlert = activeAlertCameraIds.has(camera.camera_id)

            return (
              <button
                className={`min-h-24 rounded-lg border bg-white p-3 text-left shadow-sm transition hover:border-blue-300 ${
                  isSelected ? 'border-blue-500 ring-2 ring-blue-100' : 'border-slate-200'
                }`}
                key={camera.camera_id}
                onClick={() => switchCamera(camera.camera_id)}
                type="button"
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2">
                    <Video className="shrink-0 text-slate-500" size={16} />
                    <span className="truncate font-bold text-slate-950">
                      {camera.name ?? camera.camera_id}
                    </span>
                  </span>

                  <span
                    className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                      camera.status === 'online' ? 'bg-emerald-500' : 'bg-amber-500'
                    }`}
                    title={camera.status}
                  />
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>{camera.zone}</span>
                  {isSelected && <span>{data.stats.current_count} people</span>}
                  {hasActiveAlert && (
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-1 font-bold ${
                        hasHighAlert ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-700'
                      }`}
                    >
                      <AlertTriangle size={12} />
                      Alert
                    </span>
                  )}
                </div>
              </button>
            )
          })}
        </section>

        <VideoPanel frame={data.frame} />
      </div>

      {/* Supporting live analytics */}
      <div className="mt-5 grid grid-cols-[1.2fr_0.85fr_0.95fr] gap-5">
        <TrafficChart
          summary={data.traffic_summary}
          traffic={data.traffic}
        />
        <ZoneHeatmap cells={data.zone_heatmap} />
        <AlertList alerts={data.alerts} />
      </div>
    </AppShell>
  )
}
