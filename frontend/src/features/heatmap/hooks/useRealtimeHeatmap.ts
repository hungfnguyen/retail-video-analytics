import { useEffect, useRef, useState } from 'react'
import { getLiveDashboardData } from '../../live/api/liveApi'
import type { HeatmapPoint } from '../../live/types'

const POLL_INTERVAL_MS = 2000

type RealtimeHeatmapState = {
  points: HeatmapPoint[]
  snapshotKey: number
  error: string | null
}

export function useRealtimeHeatmap(cameraId: string) {
  const [state, setState] = useState<RealtimeHeatmapState>({
    points: [],
    snapshotKey: 0,
    error: null,
  })
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    let timeoutId: ReturnType<typeof setTimeout>

    async function poll() {
      try {
        const data = await getLiveDashboardData(cameraId)
        if (mountedRef.current) {
          setState((prev) => ({
            points: data.frame.heatmap_points,
            snapshotKey: prev.snapshotKey + 1,
            error: null,
          }))
        }
      } catch {
        if (mountedRef.current) {
          setState((prev) => ({ ...prev, error: 'Unable to load realtime heatmap.' }))
        }
      } finally {
        if (mountedRef.current) {
          timeoutId = setTimeout(() => { void poll() }, POLL_INTERVAL_MS)
        }
      }
    }

    void poll()

    return () => {
      mountedRef.current = false
      clearTimeout(timeoutId)
    }
  }, [cameraId])

  return state
}
