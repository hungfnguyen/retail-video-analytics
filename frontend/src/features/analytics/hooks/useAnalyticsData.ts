import { useCallback, useEffect, useState } from 'react'
import { getAnalyticsDashboardData } from '../api/analyticsApi'
import type { AnalyticsDashboardData } from '../types'

const POLL_INTERVAL_MS = 30_000

type AnalyticsDataState = {
  data: AnalyticsDashboardData | null
  error: string | null
}

export function useAnalyticsData(days: number) {
  const [state, setState] = useState<AnalyticsDataState>({
    data: null,
    error: null,
  })

  const refresh = useCallback(async () => {
    try {
      const data = await getAnalyticsDashboardData(days)
      setState({ data, error: null })
    } catch {
      setState({ data: null, error: 'Unable to load analytics dashboard data.' })
    }
  }, [days])

  useEffect(() => {
    void refresh()
    const intervalId = window.setInterval(() => {
      void refresh()
    }, POLL_INTERVAL_MS)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [refresh])

  return { ...state, refresh }
}
