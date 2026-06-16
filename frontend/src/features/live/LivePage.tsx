import { Activity, AlertTriangle, ChevronDown, Clock, MapPin, Users, Video } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { AppShell } from '../../shared/components/AppShell'
import { MetricCard } from '../../shared/components/ui/MetricCard'
import { PageHeader } from '../../shared/components/ui/PageHeader'
import { StatusBadge } from '../../shared/components/ui/StatusBadge'
import { formatDurationMs } from '../../shared/utils/format'
import { AlertDetail } from './components/AlertDetail'
import { LiveOperationsPanel } from './components/LiveOperationsPanel'
import { QueueStatusTable } from './components/QueueStatusTable'
import { TrafficChart } from './components/TrafficChart'
import { VideoPanel } from './components/VideoPanel'
import { ZoneHeatmap } from './components/ZoneHeatmap'
import { ZoneOccupancyPanel } from './components/ZoneOccupancyPanel'
import { useLiveData } from './hooks/useLiveData'
import type { AppPage } from '../../shared/components/AppShell'
import type { Alert, ZoneCount } from './types'

type LivePageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

function zoneOccupancyCount(zoneCounts: Array<Pick<ZoneCount, 'count' | 'global_track_ids'>>) {
  const uniqueGlobalIds = new Set(
    zoneCounts.flatMap((zone) => zone.global_track_ids ?? []),
  )
  if (uniqueGlobalIds.size > 0) return uniqueGlobalIds.size
  return zoneCounts.reduce((sum, zone) => sum + Math.max(0, zone.count), 0)
}

export function LivePage({ activePage, onPageChange }: LivePageProps) {
  const { data, error, switchCamera } = useLiveData()
  const [cameraMenuOpen, setCameraMenuOpen] = useState(false)
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const prevAlertIds = useRef<Set<string>>(new Set())
  const toastTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!data?.alerts) return
    const newHigh = data.alerts.filter(
      (a) => a.severity === 'high' && !prevAlertIds.current.has(a.alert_id),
    )
    prevAlertIds.current = new Set(data.alerts.map((a) => a.alert_id))
    if (newHigh.length > 0) {
      setToast(newHigh[0].title)
      if (toastTimeout.current) clearTimeout(toastTimeout.current)
      toastTimeout.current = setTimeout(() => setToast(null), 5000)
    }
  }, [data?.alerts])

  if (error) {
    return <div className="grid min-h-screen place-items-center text-red-600">{error}</div>
  }
  if (!data) {
    return <div className="grid min-h-screen place-items-center text-slate-500">Loading live dashboard...</div>
  }

  const selectedCamera = data.cameras.find((c) => c.camera_id === data.selected_camera_id)
  const highAlertCameraIds = new Set(
    data.alerts.filter((a) => a.severity === 'high').map((a) => a.camera_id),
  )
  const activeAlertCameraIds = new Set(
    data.alerts.filter((a) => a.status === 'new').map((a) => a.camera_id),
  )
  const currentCount = Math.max(data.stats.current_count, zoneOccupancyCount(data.frame.zone_counts))

  const queueZones = data.frame.zone_counts.filter((z) => z.zone_type === 'queue')
  const queueLength = queueZones.reduce((sum, z) => sum + Math.max(0, z.count), 0)
  const longestWaitMs = Math.max(0, ...queueZones.map((z) => z.max_wait_ms ?? 0))
  const activeAlertCount = data.alerts.filter((a) => a.status === 'new').length
  const busiestZone = [...data.frame.zone_counts].sort((a, b) => b.count - a.count)[0]

  const updatedAt = new Date(data.stats.updated_at)
  const timeLabel = Number.isNaN(updatedAt.getTime())
    ? 'live'
    : updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      {/* HIGH alert toast */}
      {toast && (
        <div className="fixed right-5 top-5 z-40 flex items-center gap-3 rounded-lg border border-red-200 bg-white px-4 py-3 shadow-lg">
          <span className="h-2 w-2 shrink-0 rounded-full bg-red-500" />
          <span className="text-sm font-semibold text-slate-900">{toast}</span>
          <button className="ml-2 text-slate-400 hover:text-slate-600" onClick={() => setToast(null)} type="button">×</button>
        </div>
      )}

      <PageHeader
        title="Live Monitor"
        subtitle={`Store A · updated ${timeLabel}`}
        badge={<StatusBadge status="live" />}
        actions={
          <div className="relative">
            <button
              className="flex min-w-48 items-center justify-between gap-6 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-medium text-slate-800 shadow-sm hover:border-slate-300"
              onClick={() => setCameraMenuOpen((p) => !p)}
              onBlur={() => setTimeout(() => setCameraMenuOpen(false), 150)}
              type="button"
            >
              {selectedCamera?.name ?? data.selected_camera_id}
              <ChevronDown size={15} />
            </button>
            {cameraMenuOpen && (
              <div className="absolute right-0 z-50 mt-1 w-full rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
                {data.cameras.map((camera) => (
                  <button
                    className={`w-full px-3.5 py-2 text-left text-sm hover:bg-blue-50 ${
                      camera.camera_id === data.selected_camera_id ? 'font-bold text-blue-600' : 'text-slate-700'
                    }`}
                    key={camera.camera_id}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => { switchCamera(camera.camera_id); setCameraMenuOpen(false) }}
                    type="button"
                  >
                    {camera.name ?? camera.camera_id}
                  </button>
                ))}
              </div>
            )}
          </div>
        }
      />

      {/* KPI row — 5 cards */}
      <div className="mb-5 grid grid-cols-5 gap-3">
        <MetricCard label="Visitors in Store" value={currentCount} icon={Users} tone="blue" meta={`updated ${timeLabel}`} />
        <MetricCard label="Queue Length" value={queueLength} icon={Activity} tone="amber" meta="People in queue zones" />
        <MetricCard label="Longest Wait" value={longestWaitMs > 0 ? formatDurationMs(longestWaitMs) : '—'} icon={Clock} tone={longestWaitMs > 120000 ? 'red' : longestWaitMs > 60000 ? 'amber' : 'green'} meta="Max queue wait" />
        <MetricCard label="Busiest Zone" value={busiestZone?.zone_name ?? busiestZone?.zone_id ?? '—'} icon={MapPin} tone="violet" meta={busiestZone ? `${busiestZone.count} people` : 'No zone data'} />
        <MetricCard label="Active Alerts" value={activeAlertCount} icon={AlertTriangle} tone={activeAlertCount > 0 ? 'red' : 'green'} meta={activeAlertCount > 0 ? 'Needs review' : 'All clear'} />
      </div>

      {/* Camera thumbnails */}
      <section className="mb-5 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3" aria-label="Camera overview">
        {data.cameras.map((camera) => {
          const isSelected = camera.camera_id === data.selected_camera_id
          const hasHighAlert = highAlertCameraIds.has(camera.camera_id)
          const hasActiveAlert = activeAlertCameraIds.has(camera.camera_id)
          return (
            <button
              className={`min-h-20 rounded-lg border bg-white p-3 text-left shadow-sm transition hover:border-blue-300 ${isSelected ? 'border-blue-500 ring-2 ring-blue-100' : 'border-slate-200'}`}
              key={camera.camera_id}
              onClick={() => switchCamera(camera.camera_id)}
              type="button"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="flex min-w-0 items-center gap-1.5">
                  <Video className="shrink-0 text-slate-400" size={14} />
                  <span className="truncate text-sm font-bold text-slate-900">{camera.name ?? camera.camera_id}</span>
                </span>
                {hasActiveAlert && <AlertTriangle className="shrink-0 text-amber-500" size={14} />}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                <span>{camera.zone}</span>
                {isSelected && <span>{currentCount} people</span>}
                {hasActiveAlert && (
                  <span className={`rounded-full px-1.5 py-0.5 font-semibold ${hasHighAlert ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-600'}`}>Alert</span>
                )}
              </div>
            </button>
          )
        })}
      </section>

      {/* Main grid: Video + Operations panel */}
      <div className="mb-5 grid grid-cols-[minmax(0,1.45fr)_420px] gap-5">
        <VideoPanel frame={data.frame} />
        <LiveOperationsPanel alerts={data.alerts} zoneCounts={data.frame.zone_counts} onAlertClick={setSelectedAlert} />
      </div>

      {/* Secondary grid: Queue table + Traffic chart + Zone occupancy */}
      <div className="mb-5 grid grid-cols-3 gap-5">
        <QueueStatusTable zoneCounts={data.frame.zone_counts} />
        <TrafficChart traffic={data.traffic} summary={data.traffic_summary} />
        <ZoneOccupancyPanel zoneCounts={data.frame.zone_counts} />
      </div>

      {/* Compact density strip */}
      <ZoneHeatmap cells={data.zone_heatmap} />

      {selectedAlert && (
        <AlertDetail alert={selectedAlert} onClose={() => setSelectedAlert(null)} />
      )}
    </AppShell>
  )
}
