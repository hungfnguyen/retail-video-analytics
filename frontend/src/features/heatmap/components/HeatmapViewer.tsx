import { EmptyState } from '../../../shared/components/ui/EmptyState'
import { HeatmapCanvas } from './HeatmapCanvas'
import type { PresenceHeatmapData } from '../../analytics/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type HeatmapViewerProps = {
  cameraId: string
  data: PresenceHeatmapData | null
  loading: boolean
  error: string | null
  opacity?: number
}

export function HeatmapViewer({ cameraId, data, loading, error, opacity = 100 }: HeatmapViewerProps) {
  const isEmpty = data?.data_status === 'empty' || (data?.data_status === 'ready' && data.cells.length === 0)
  const isError = !!error || data?.data_status === 'error'

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Customer Presence Density</h3>
          <p className="text-xs text-slate-400">Presence · normalized density</p>
        </div>
        {loading && <span className="text-xs font-medium text-slate-400">Refreshing…</span>}
      </div>

      {isError && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">
          Data warehouse unavailable — Trino may still be starting. Please refresh.
        </p>
      )}

      {isEmpty ? (
        <EmptyState
          title="No presence data for this period"
          description="Run the heatmap Gold aggregation for this camera to populate the view."
        />
      ) : (
        <div
          className="relative w-full overflow-hidden rounded-lg bg-slate-900"
          style={{ aspectRatio: '16 / 9' }}
        >
          <img
            alt={`Camera ${cameraId} reference`}
            className="absolute inset-0 h-full w-full object-contain"
            src={`${API_BASE_URL}/media/live/${cameraId}/snapshot.jpg`}
          />
          {data?.cells && (
            <HeatmapCanvas
              cells={data.cells}
              gridCols={data.grid_cols}
              gridRows={data.grid_rows}
              opacity={opacity}
            />
          )}
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-900/40">
              <span className="text-sm font-semibold text-white">Loading…</span>
            </div>
          )}
        </div>
      )}

      <div className="mt-3 grid grid-cols-[auto_1fr_auto] items-center gap-2 text-xs text-slate-500">
        <span>Low</span>
        <div className="h-2 rounded-full bg-gradient-to-r from-blue-500 via-green-400 via-yellow-300 to-red-500" />
        <span>High</span>
      </div>
    </div>
  )
}
