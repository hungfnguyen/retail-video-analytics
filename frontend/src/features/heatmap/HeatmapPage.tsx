import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { AppShell, type AppPage } from '../../shared/components/AppShell'
import { PageHeader } from '../../shared/components/ui/PageHeader'
import { useHeatmapData } from './hooks/useHeatmapData'
import { HeatmapInsightsPanel } from './components/HeatmapInsightsPanel'
import { HeatmapSettingsPanel } from './components/HeatmapSettingsPanel'
import { HeatmapViewer } from './components/HeatmapViewer'
import { TopHotspotsList } from './components/TopHotspotsList'
import { datePresetToDays } from '../analytics/components/AnalyticsFilterBar'
import type { DatePreset } from '../analytics/components/AnalyticsFilterBar'

type HeatmapPageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

// Static list — future API-driven camera list can replace this constant
const CAMERA_IDS = ['cam_01', 'cam_02']

const PRESET_LABELS: Record<DatePreset, string> = {
  today: 'Today',
  last_7_days: 'Last 7 days',
  last_14_days: 'Last 14 days',
  last_30_days: 'Last 30 days',
}

export function HeatmapPage({ activePage, onPageChange }: HeatmapPageProps) {
  const [cameraId, setCameraId] = useState(CAMERA_IDS[0])
  const [preset, setPreset] = useState<DatePreset>('last_7_days')
  const [opacity, setOpacity] = useState(80)

  const days = datePresetToDays[preset]
  const { data, loading, error, refresh } = useHeatmapData(cameraId, days)

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      <PageHeader
        title="Heatmap"
        subtitle="Customer presence density by camera and period"
        actions={
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
              {CAMERA_IDS.map((id) => (
                <button
                  className={`rounded-md px-3 py-2 text-sm font-semibold transition ${
                    cameraId === id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                  key={id}
                  onClick={() => setCameraId(id)}
                  type="button"
                >
                  {id}
                </button>
              ))}
            </div>

            <select
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm focus:border-blue-400 focus:outline-none"
              value={preset}
              onChange={(e) => setPreset(e.target.value as DatePreset)}
            >
              {(Object.entries(PRESET_LABELS) as [DatePreset, string][]).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>

            <button
              className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:border-blue-300 hover:text-blue-700 transition disabled:opacity-50"
              disabled={loading}
              onClick={() => void refresh()}
              title="Refresh heatmap"
              type="button"
            >
              <RefreshCw className={loading ? 'animate-spin' : ''} size={15} />
            </button>
          </div>
        }
      />

      {/* Main grid: Viewer (left) + Side panel (right) */}
      <div className="grid grid-cols-[minmax(0,1.6fr)_320px] gap-5">
        <HeatmapViewer
          cameraId={cameraId}
          data={data}
          loading={loading}
          error={error}
          opacity={opacity}
        />

        <div className="flex flex-col gap-4">
          <HeatmapSettingsPanel opacity={opacity} onOpacityChange={setOpacity} />
          <HeatmapInsightsPanel data={data} />
          <TopHotspotsList data={data} />
        </div>
      </div>
    </AppShell>
  )
}
