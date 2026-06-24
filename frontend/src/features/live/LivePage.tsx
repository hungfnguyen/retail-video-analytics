import {
  AlertTriangle,
  Bell,
  ChevronDown,
  Clock3,
  Expand,
  RefreshCw,
  TimerReset,
  Users,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { AppShell } from '../../shared/components/AppShell'
import type { AppPage } from '../../shared/components/AppShell'
import { MetricCard } from '../../shared/components/ui/MetricCard'
import { PageHeader } from '../../shared/components/ui/PageHeader'
import { StatusBadge } from '../../shared/components/ui/StatusBadge'
import { formatDuration, formatDurationMs } from '../../shared/utils/format'
import { AlertDetail } from './components/AlertDetail'
import { AlertList } from './components/AlertList'
import { QueueStatusTable } from './components/QueueStatusTable'
import { VideoPanel } from './components/VideoPanel'
import { ZoneOccupancyPanel } from './components/ZoneOccupancyPanel'
import { useLiveData } from './hooks/useLiveData'
import type { Alert, ZoneCount } from './types'

type LivePageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

function zoneOccupancyCount(zoneCounts: Array<Pick<ZoneCount, 'count' | 'global_track_ids'>>) {
  const uniqueGlobalIds = new Set(zoneCounts.flatMap((z) => z.global_track_ids ?? []))
  if (uniqueGlobalIds.size > 0) return uniqueGlobalIds.size
  return zoneCounts.reduce((sum, z) => sum + Math.max(0, z.count), 0)
}

function formatDeltaSeconds(deltaSec: number, compareLabel = 'vs yesterday') {
  if (!Number.isFinite(deltaSec) || Math.abs(deltaSec) < 1) {
    return { value: `Stable ${compareLabel}`, tone: 'neutral' as const }
  }
  const absText = formatDuration(Math.abs(deltaSec))
  if (deltaSec > 0) {
    return { value: `↑ ${absText} ${compareLabel}`, tone: 'negative' as const }
  }
  return { value: `↓ ${absText} ${compareLabel}`, tone: 'positive' as const }
}

function liveStatusTone(status: string, metadataStatus: string) {
  if (status === 'critical' || metadataStatus === 'stale' || metadataStatus === 'missing') return 'red' as const
  if (status === 'warning' || metadataStatus === 'lagging') return 'amber' as const
  return 'green' as const
}

export function LivePage({ activePage, onPageChange }: LivePageProps) {
  const { data, error, switchCamera, refresh } = useLiveData()
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
    return <div className="grid min-h-screen place-items-center text-slate-500">Loading live dashboard…</div>
  }

  const selectedCamera = data.cameras.find((c) => c.camera_id === data.selected_camera_id)
  const queueZones = data.frame.zone_counts.filter((z) => z.zone_type === 'queue')
  const totalQueuePeople = queueZones.reduce((sum, z) => sum + Math.max(0, z.count), 0)
  const currentCount = Math.max(data.stats.current_count, zoneOccupancyCount(data.frame.zone_counts))
  const activeAlertCount = data.alerts.filter((a) => a.status === 'new').length
  const avgQueueWaitMs = totalQueuePeople > 0
    ? queueZones.reduce((sum, z) => sum + (z.avg_wait_ms ?? 0) * Math.max(0, z.count), 0) / totalQueuePeople
    : 0

  const peakHourLabel = data.insights.peak_hour || data.traffic_summary.peak_time || '--'
  const peakHourVisitors = data.insights.peak_hour_visitors || data.traffic_summary.peak_count

  const updatedAt = new Date(data.stats.updated_at)
  const timeLabel = Number.isNaN(updatedAt.getTime())
    ? 'live'
    : updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

  const queueTrend = totalQueuePeople > 0 ? formatDeltaSeconds(data.insights.avg_queue_wait_delta_sec) : undefined

  const headerActions = (
      <div className="flex items-center gap-2">
        <div className="relative">
          <button
            className="flex min-w-44 items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-medium text-slate-700 shadow-sm hover:border-slate-300"
            onClick={() => setCameraMenuOpen((open) => !open)}
            onBlur={() => setTimeout(() => setCameraMenuOpen(false), 150)}
            type="button"
          >
            {selectedCamera?.name ?? data.selected_camera_id}
            <ChevronDown size={14} />
          </button>
          {cameraMenuOpen && (
            <div className="absolute right-0 z-50 mt-1 w-full rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
              {data.cameras.map((camera) => (
                <button
                  className={`w-full px-3.5 py-2 text-left text-sm hover:bg-blue-50 ${
                    camera.camera_id === data.selected_camera_id ? 'font-semibold text-blue-600' : 'text-slate-700'
                  }`}
                  key={camera.camera_id}
                  onMouseDown={(event) => event.preventDefault()}
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

        <button
          className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-slate-300 hover:text-slate-700"
          onClick={refresh}
          type="button"
        >
          <RefreshCw size={16} />
        </button>
        <button
          className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-slate-300 hover:text-slate-700"
          type="button"
        >
          <Expand size={16} />
        </button>
        <div className="relative">
          <button
            className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-slate-300 hover:text-slate-700"
            type="button"
          >
            <Bell size={16} />
          </button>
          {activeAlertCount > 0 && (
            <span className="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
              {activeAlertCount}
            </span>
          )}
        </div>
      </div>
  )

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      {toast && (
        <div className="fixed right-5 top-5 z-40 flex items-center gap-3 rounded-xl border border-red-200 bg-white px-4 py-3 shadow-lg">
          <span className="h-2 w-2 shrink-0 rounded-full bg-red-500" />
          <span className="text-sm font-semibold text-slate-900">{toast}</span>
          <button className="ml-2 text-slate-400 hover:text-slate-600" onClick={() => setToast(null)} type="button">
            ×
          </button>
        </div>
      )}

      <PageHeader
        title="Live Monitor"
        subtitle={`${data.store.name} · Updated ${timeLabel}`}
        badge={<StatusBadge status="live" />}
        actions={headerActions}
      />

      <div className="mb-6 grid grid-cols-4 gap-4">
        <MetricCard
          icon={Users}
          label="Visitors in Store"
          meta="Current store occupancy"
          tone="blue"
          trend={
            data.stats.count_change_percent !== 0
              ? {
                  value: `${data.stats.count_change_percent > 0 ? '↑' : '↓'} ${Math.abs(data.stats.count_change_percent)}% vs previous`,
                  tone: data.stats.count_change_percent > 0 ? 'positive' : 'neutral',
                }
              : undefined
          }
          value={currentCount}
        />
        <MetricCard
          icon={TimerReset}
          label="Avg Queue Wait"
          meta={totalQueuePeople > 0 ? `${totalQueuePeople} people in queue` : 'No active queue'}
          tone={avgQueueWaitMs > 120000 ? 'red' : avgQueueWaitMs > 60000 ? 'amber' : 'violet'}
          trend={queueTrend}
          value={avgQueueWaitMs > 0 ? formatDurationMs(avgQueueWaitMs) : '—'}
        />
        <MetricCard
          icon={Clock3}
          label="Peak Hour"
          meta={peakHourVisitors > 0 ? `${peakHourVisitors} visitors` : 'No historical traffic yet'}
          tone="amber"
          value={peakHourLabel}
        />
        <MetricCard
          icon={AlertTriangle}
          label="Active Alerts"
          meta={activeAlertCount > 0 ? `${activeAlertCount} require review` : 'All clear'}
          tone={liveStatusTone(data.stats.status, data.stats.metadata_status)}
          trend={
            activeAlertCount > 0
              ? { value: `${activeAlertCount} new`, tone: 'negative' }
              : { value: 'No new incidents', tone: 'positive' }
          }
          value={activeAlertCount}
        />
      </div>

      <div className="mb-6 grid grid-cols-[minmax(0,1.52fr)_360px] gap-5">
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-slate-900">
                Live Camera
                {selectedCamera && (
                  <span className="font-normal text-slate-500">
                    {' '}· {selectedCamera.name ?? selectedCamera.camera_id}
                    {selectedCamera.zone ? ` · ${selectedCamera.zone}` : ''}
                  </span>
                )}
              </span>
            </div>
            <StatusBadge status="live" />
          </div>
          <VideoPanel frame={data.frame} />
        </div>

        <AlertList alerts={data.alerts} onAlertClick={setSelectedAlert} />
      </div>

      <div className="grid grid-cols-2 gap-5">
        <QueueStatusTable zoneCounts={data.frame.zone_counts} />
        <ZoneOccupancyPanel zoneCounts={data.frame.zone_counts} />
      </div>

      {selectedAlert && (
        <AlertDetail alert={selectedAlert} onClose={() => setSelectedAlert(null)} />
      )}
    </AppShell>
  )
}
