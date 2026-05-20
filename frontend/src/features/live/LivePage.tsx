import { ChevronDown } from 'lucide-react'
import { AppShell } from '../../shared/components/AppShell'
import { AlertList } from './components/AlertList'
import { LiveMetricCards } from './components/LiveMetricCards'
import { PipelineHealth } from './components/PipelineHealth'
import { TrafficChart } from './components/TrafficChart'
import { VideoPanel } from './components/VideoPanel'
import { ZoneHeatmap } from './components/ZoneHeatmap'
import { useLiveData } from './hooks/useLiveData'

export function LivePage() {
  const { data, error } = useLiveData()


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
    <AppShell>
      {/* Page header */}
      <header className="mb-5 flex items-center justify-between">
        <h1 className="m-0 text-[26px] font-bold leading-tight text-slate-950">Live Store Monitor</h1>

        <div className="flex items-center gap-3">
          <button
            className="flex min-w-55 items-center justify-between gap-8 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-slate-950 shadow-sm"
            type="button"
          >
            {data.store.name}
            <ChevronDown size={16} />
          </button>

          <button
            className="flex min-w-55 items-center justify-between gap-8 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-slate-950 shadow-sm"
            type="button"
          >
            {selectedCamera?.name ?? data.selected_camera_id}
            <ChevronDown size={16} />
          </button>

          <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-4.5 py-2.5 font-bold text-emerald-700">
            Running
          </span>
        </div>
      </header>

      {/* Primary live monitoring area */}
      <div className="grid grid-cols-[minmax(600px,1.2fr)_minmax(430px,0.8fr)] gap-5">
        <VideoPanel frame={data.frame} />

        <div className="grid gap-4.5">
          <LiveMetricCards stats={data.stats} />
          <AlertList alerts={data.alerts} />
        </div>
      </div>

      {/* Supporting live analytics */}
      <div className="mt-5 grid grid-cols-[1.15fr_1fr_1fr] gap-5">
        <TrafficChart
          summary={data.traffic_summary}
          traffic={data.traffic}
        />
        <ZoneHeatmap cells={data.zone_heatmap} />
        <PipelineHealth services={data.pipeline_health} />
      </div>
    </AppShell>
  )
}
