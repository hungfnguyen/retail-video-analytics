import { useEffect, useState } from 'react'
import { getLiveDashboardData } from '../api/liveApi'
import type { LiveDashboardData } from '../types'

const POLL_INTERVAL_MS = 1000

type LiveDataState = {
  data: LiveDashboardData | null
  error: string | null
}

export function useLiveData(cameraId = 'cam_01') {
  const [state, setState] = useState<LiveDataState>({
    data: null,
    error: null,
  })

  useEffect(() => {
    let isMounted = true

    async function fetchData() {
      try {
        const data = await getLiveDashboardData(cameraId)
        if (isMounted) {
          setState({ data, error: null })
        }
      } catch {
        if (isMounted) {
          setState({ data: null, error: 'Unable to load live dashboard data.' })
        }
      }
    }

    void fetchData()
    const intervalId = window.setInterval(() => {
      void fetchData()
    }, POLL_INTERVAL_MS)

    return () => {
      isMounted = false
      window.clearInterval(intervalId)
    }
  }, [cameraId])

  return state
}
