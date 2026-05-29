import { useCallback, useEffect, useState } from 'react'
import { getSystemDashboardData } from '../api/systemApi'
import type { SystemDashboardData } from '../types'

const POLL_INTERVAL_MS = 10_000

type SystemDataState = {
  data: SystemDashboardData | null
  error: string | null
}

export function useSystemData(cameraId = 'cam_01') {
  const [state, setState] = useState<SystemDataState>({
    data: null,
    error: null,
  })

  const refresh = useCallback(async () => {
    try {
      const data = await getSystemDashboardData(cameraId)
      setState({ data, error: null })
    } catch {
      setState({ data: null, error: 'Unable to load system dashboard data.' })
    }
  }, [cameraId])

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
