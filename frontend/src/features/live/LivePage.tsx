import { useState } from 'react'
import { AppShell } from '../../shared/components/AppShell'
import { AlertList } from './components/AlertList'
import { LiveMetricCards } from './components/LiveMetricCards'
import { VideoPanel } from './components/VideoPanel'
import { ZoneHeatmap } from './components/ZoneHeatmap'
import { useLiveData } from './hooks/useLiveData'
import type { AppPage } from '../../shared/components/AppShell'

type LivePageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

export function LivePage({ activePage, onPageChange }: LivePageProps) {
  const [selectedCameraId, setSelectedCameraId] = useState('cam_01')
  const { data, error } = useLiveData(selectedCameraId)


  if (error) {
    return <div className="grid min-h-screen place-items-center">{error}</div>
  }

  if (!data) {
    return <div className="grid min-h-screen place-items-center">Loading live dashboard...</div>
  }

  const selectedCamera = data.cameras.find(
    (camera) => camera.camera_id === data.selected_camera_id,
  )

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      {/* Page header */}
      <header className="mb-5 flex items-center justify-between">
        <h1 className="m-0 text-[26px] font-bold leading-tight text-slate-950">Live Store Monitor</h1>

        <div className="flex items-center gap-3">
          <select
            className="min-w-55 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 font-semibold text-slate-950 shadow-sm"
            onChange={(event) => setSelectedCameraId(event.target.value)}
            value={selectedCamera?.camera_id ?? selectedCameraId}
          >
            {data.cameras.map((camera) => (
              <option key={camera.camera_id} value={camera.camera_id}>
                {camera.name}
              </option>
            ))}
          </select>

          <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-4.5 py-2.5 font-bold text-emerald-700">
            Running
          </span>
        </div>
      </header>

      <LiveMetricCards stats={data.stats} />

      {/* Primary live monitoring area */}
      <div className="mt-5 grid grid-cols-[minmax(680px,1.45fr)_minmax(360px,0.55fr)] gap-5">
        <VideoPanel frame={data.frame} />

        <div className="grid gap-4.5">
          <AlertList alerts={data.alerts} />
        </div>
      </div>

      {/* Realtime spatial state */}
      <div className="mt-5 grid grid-cols-[minmax(0,1fr)] gap-5">
        <ZoneHeatmap cells={data.zone_heatmap} />
      </div>
    </AppShell>
  )
}
