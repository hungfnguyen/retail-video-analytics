import { AlertTriangle, ChevronDown, Video } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { AppShell } from '../../shared/components/AppShell'
import { AlertDetail } from './components/AlertDetail'
import { AlertList } from './components/AlertList'
import { LiveMetricCards } from './components/LiveMetricCards'
import { VideoPanel } from './components/VideoPanel'
import { ZoneHeatmap } from './components/ZoneHeatmap'
import { ZoneRuntimePanel } from './components/ZoneRuntimePanel'
import { useLiveData } from './hooks/useLiveData'
import type { AppPage } from '../../shared/components/AppShell'
import type { Alert } from './types'

type LivePageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

function zoneOccupancyCount(zoneCounts: Array<{ count: number, global_track_ids?: string[] }>) {
  const uniqueGlobalIds = new Set(
    zoneCounts.flatMap((zone) => zone.global_track_ids ?? []),
  )
  if (uniqueGlobalIds.size > 0) {
    return uniqueGlobalIds.size
  }

  return zoneCounts.reduce((sum, zone) => sum + Math.max(0, zone.count), 0)
}

export function LivePage({ activePage, onPageChange }: LivePageProps) {
  const { data, error, switchCamera } = useLiveData()
  const [cameraMenuOpen, setCameraMenuOpen] = useState(false)
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const prevAlertIds = useRef<Set<string>>(new Set())
  const toastTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Detect new HIGH alerts and show a toast
  useEffect(() => {
    if (!data?.alerts) return
    const current = data.alerts
    const newHigh = current.filter(
      (a) => a.severity === 'high' && !prevAlertIds.current.has(a.alert_id),
    )
    prevAlertIds.current = new Set(current.map((a) => a.alert_id))

    if (newHigh.length > 0) {
      setToast(newHigh[0].title)
      if (toastTimeout.current) clearTimeout(toastTimeout.current)
      toastTimeout.current = setTimeout(() => setToast(null), 5000)
    }
  }, [data?.alerts])

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
  const currentPeopleCount = Math.max(
    data.stats.current_count,
    zoneOccupancyCount(data.frame.zone_counts),
  )

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      {/* HIGH alert toast */}
      {toast && (
        <div className="fixed right-5 top-5 z-40 flex items-center gap-3 rounded-lg border border-red-200 bg-white px-4 py-3 shadow-lg">
          <span className="h-2 w-2 shrink-0 rounded-full bg-red-500" />
          <span className="text-sm font-semibold text-slate-900">{toast}</span>
          <button
            className="ml-2 text-slate-400 hover:text-slate-600"
            onClick={() => setToast(null)}
            type="button"
          >
            ×
          </button>
        </div>
      )}

      {/* Page header */}
      <header className="mb-5 flex items-center justify-between">
        <h1 className="m-0 text-[26px] font-bold leading-tight text-slate-950">Live Store Monitor</h1>

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
                  {camera.name ?? camera.camera_id}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      {/* Primary live monitoring area */}
      <div className="grid gap-5">
        <LiveMetricCards
          alerts={data.alerts}
          stats={data.stats}
          zoneCounts={data.frame.zone_counts}
        />

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

                  {hasActiveAlert && <AlertTriangle className="shrink-0 text-amber-600" size={15} />}
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>{camera.zone}</span>
                  {isSelected && <span>{currentPeopleCount} people</span>}
                  {hasActiveAlert && (
                    <span className={`rounded-full px-2 py-1 font-bold ${
                      hasHighAlert ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-700'
                    }`}
                    >
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

      <div className="mt-5 grid grid-cols-[1.35fr_0.75fr] gap-5">
        <ZoneRuntimePanel
          lineCrossings={data.frame.line_crossings}
          zoneCounts={data.frame.zone_counts}
        />
        <AlertList alerts={data.alerts} onAlertClick={setSelectedAlert} />
      </div>

      <div className="mt-5">
        <ZoneHeatmap cells={data.zone_heatmap} />
      </div>

      {selectedAlert && (
        <AlertDetail alert={selectedAlert} onClose={() => setSelectedAlert(null)} />
      )}
    </AppShell>
  )
}
