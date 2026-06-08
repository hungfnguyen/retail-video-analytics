import { Database } from 'lucide-react'
import { useHeatmapData } from '../hooks/useHeatmapData'
import { HeatmapCanvas } from './HeatmapCanvas'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type TrafficHeatmapProps = {
  cameraId: string
  days: number
}

export function TrafficHeatmap({ cameraId, days }: TrafficHeatmapProps) {
  const { data, loading, error } = useHeatmapData(cameraId, days)

  const isEmpty = data?.data_status === 'empty'
  const isError = !!error || data?.data_status === 'error'

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="m-0 text-[17px] font-bold text-slate-950">Traffic density</h2>
        <span className="rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">
          32×24 grid · silver_detections_v2 · log₁₊ norm
        </span>
      </div>

      {isError && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">
          {error ?? data?.error_message ?? 'Query failed'}
        </p>
      )}

      {isEmpty ? (
        <div className="grid min-h-[360px] place-items-center rounded-md border border-dashed border-slate-300 bg-slate-50">
          <div className="text-center">
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-lg bg-slate-100 text-slate-500">
              <Database size={22} />
            </span>
            <p className="mt-3 text-sm font-semibold text-slate-500">
              No detection rows in silver_detections_v2 for this period.
            </p>
          </div>
        </div>
      ) : (
        <div
          className="relative w-full overflow-hidden rounded-md bg-slate-900"
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
    </section>
  )
}
