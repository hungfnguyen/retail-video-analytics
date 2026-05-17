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
    return <div className="page-state">{error}</div>
  }

  if (!data) {
    return <div className="page-state">Loading live dashboard...</div>
  }

  const selectedCamera = data.cameras.find(
    (camera) => camera.camera_id === data.selected_camera_id,
  )

  return (
    <AppShell>
      <header className="topbar">
        <h1>Live Store Monitor</h1>
        <div className="topbar-controls">
          <button className="selector" type="button">
            {data.store.name}
            <ChevronDown size={16} />
          </button>
          <button className="selector" type="button">
            {selectedCamera?.name ?? data.selected_camera_id}
            <ChevronDown size={16} />
          </button>
          <span className="run-status">Running</span>
        </div>
      </header>

      <div className="live-layout">
        <VideoPanel frame={data.frame} />
        <div className="live-side">
          <LiveMetricCards stats={data.stats} />
          <AlertList alerts={data.alerts} />
        </div>
      </div>

      <div className="live-bottom-grid">
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
