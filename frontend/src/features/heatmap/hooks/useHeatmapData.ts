import { useCallback, useEffect, useState } from 'react'
import { getPresenceHeatmapData } from '../../analytics/api/analyticsApi'
import type { PresenceHeatmapData } from '../../analytics/types'

type HeatmapDataState = {
  data: PresenceHeatmapData | null
  loading: boolean
  error: string | null
}

export function useHeatmapData(cameraId: string, days: number) {
  const [state, setState] = useState<HeatmapDataState>({
    data: null,
    loading: false,
    error: null,
  })

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const data = await getPresenceHeatmapData(cameraId, days)
      setState({ data, loading: false, error: null })
    } catch {
      setState({ data: null, loading: false, error: 'Unable to load heatmap data.' })
    }
  }, [cameraId, days])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { ...state, refresh }
}
