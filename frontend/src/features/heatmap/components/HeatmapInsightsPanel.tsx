import { getHeatmapStats } from '../adapters/heatmapViewModels'
import type { PresenceHeatmapData } from '../../analytics/types'

type HeatmapInsightsPanelProps = {
  data: PresenceHeatmapData | null
}

function concentrationLabel(score: number): string {
  if (score >= 0.2) return 'High'
  if (score >= 0.08) return 'Medium'
  return 'Low'
}

function concentrationColor(score: number): string {
  if (score >= 0.2) return 'text-red-600'
  if (score >= 0.08) return 'text-amber-600'
  return 'text-emerald-600'
}

function recommendedAction(score: number): string {
  if (score >= 0.2) return 'High foot traffic concentration — consider redistributing product displays or adding staff in these zones.'
  if (score >= 0.08) return 'Moderate congestion detected. Monitor peak hours and consider layout adjustments.'
  return 'Traffic is well-distributed. Current layout appears effective.'
}

export function HeatmapInsightsPanel({ data }: HeatmapInsightsPanelProps) {
  const stats = getHeatmapStats(data)

  if (!stats.dataAvailable) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-2 text-sm font-semibold text-slate-800">Insights</h3>
        <p className="text-xs text-slate-400">No heatmap data available for this camera / period.</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Insights</h3>
      <div className="grid gap-2.5">
        <div className="flex items-start justify-between gap-2">
          <span className="text-xs text-slate-500">Hottest area</span>
          <span className="text-xs font-semibold text-slate-800 capitalize">{stats.hottestAreaLabel}</span>
        </div>
        <div className="flex items-start justify-between gap-2">
          <span className="text-xs text-slate-500">Concentration</span>
          <span className={`text-xs font-bold ${concentrationColor(stats.concentrationScore)}`}>
            {concentrationLabel(stats.concentrationScore)}
          </span>
        </div>
        <div className="flex items-start justify-between gap-2">
          <span className="text-xs text-slate-500">Hotspot cells</span>
          <span className="text-xs font-semibold text-slate-800">{stats.hotspotCount}</span>
        </div>
        <div className="mt-1 rounded-lg bg-blue-50 p-2.5">
          <p className="text-[11px] font-medium leading-relaxed text-blue-700">
            {recommendedAction(stats.concentrationScore)}
          </p>
        </div>
      </div>
    </div>
  )
}
