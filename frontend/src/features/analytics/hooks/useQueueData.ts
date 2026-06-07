import { useCallback, useEffect, useState } from 'react'
import { getQueueAnalyticsData } from '../api/analyticsApi'
import type { QueueAnalyticsData } from '../types'

const POLL_INTERVAL_MS = 30_000

type QueueDataState = {
  data: QueueAnalyticsData | null
  error: string | null
}

export function useQueueData(days: number) {
  const [state, setState] = useState<QueueDataState>({ data: null, error: null })

  const refresh = useCallback(async () => {
    try {
      const data = await getQueueAnalyticsData(days)
      setState({ data, error: null })
    } catch {
      setState({ data: null, error: 'Unable to load queue analytics data.' })
    }
  }, [days])

  useEffect(() => {
    void refresh()
    const intervalId = window.setInterval(() => { void refresh() }, POLL_INTERVAL_MS)
    return () => { window.clearInterval(intervalId) }
  }, [refresh])

  return { ...state, refresh }
}
