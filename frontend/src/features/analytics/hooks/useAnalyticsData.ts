import { useCallback, useEffect, useState } from 'react'
import { getAnalyticsDashboardData } from '../api/analyticsApi'
import type { AnalyticsDashboardData } from '../types'

const POLL_INTERVAL_MS = 30_000

type AnalyticsDataState = {
  data: AnalyticsDashboardData | null
  error: string | null
}

export function useAnalyticsData(days: number, cameraId?: string | null) {
  const [state, setState] = useState<AnalyticsDataState>({
    data: null,
    error: null,
  })

  const refresh = useCallback(async () => {
    try {
      const data = await getAnalyticsDashboardData(days, cameraId)
      setState({ data, error: null })
    } catch {
      setState({ data: null, error: 'Unable to load analytics dashboard data.' })
    }
  }, [cameraId, days])

  useEffect(() => {
    const initialId = window.setTimeout(() => {
      void refresh()
    }, 0)

    const intervalId = window.setInterval(() => {
      void refresh()
    }, POLL_INTERVAL_MS)

    return () => {
      window.clearTimeout(initialId)
      window.clearInterval(intervalId)
    }
  }, [refresh])

  return { ...state, refresh }
}
