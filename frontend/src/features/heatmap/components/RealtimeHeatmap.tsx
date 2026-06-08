import { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type RealtimeHeatmapProps = {
  cameraId: string
}

export function RealtimeHeatmap({ cameraId }: RealtimeHeatmapProps) {
  const [key, setKey] = useState(0)

  // Increment key every 2s so the browser re-fetches the latest heatmap.jpg
  useEffect(() => {
    const id = setInterval(() => setKey((k) => k + 1), 2000)
    return () => clearInterval(id)
  }, [])

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.06)]">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="m-0 text-[17px] font-bold text-slate-950">Realtime occupancy</h2>
        <span className="rounded-md bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">
          supervision HeatMapAnnotator · 2 s refresh
        </span>
      </div>

      <div
        className="relative w-full overflow-hidden rounded-md bg-slate-900"
        style={{ aspectRatio: '16 / 9' }}
      >
        <img
          alt={`Camera ${cameraId} realtime heatmap`}
          className="absolute inset-0 h-full w-full object-contain"
          src={`${API_BASE_URL}/media/live/${cameraId}/heatmap.jpg?k=${key}`}
        />
      </div>

      <div className="mt-3 grid grid-cols-[auto_1fr_auto] items-center gap-2 text-xs text-slate-500">
        <span>Low</span>
        <div className="h-2 rounded-full bg-gradient-to-r from-blue-600 via-green-400 via-yellow-300 to-red-500" />
        <span>High</span>
      </div>
    </section>
  )
}
