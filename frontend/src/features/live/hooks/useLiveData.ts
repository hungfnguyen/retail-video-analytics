import { useCallback, useEffect, useState } from 'react'
import { getLiveDashboardData } from '../api/liveApi'
import type { LiveDashboardData } from '../types'

const POLL_INTERVAL_MS = 2000

type LiveDataState = {
  data: LiveDashboardData | null
  error: string | null
}

export function useLiveData() {
  const [cameraId, setCameraId] = useState('cam_01')
  const [state, setState] = useState<LiveDataState>({
    data: null,
    error: null,
  })

  useEffect(() => {
    let isMounted = true
    let timeoutId: ReturnType<typeof setTimeout>

    async function fetchData() {
      try {
        const data = await getLiveDashboardData(cameraId)
        if (isMounted) {
          setState({ data, error: null })
        }
      } catch {
        if (isMounted) {
          setState((prev) => ({ ...prev, error: 'Unable to load live dashboard data.' }))
        }
      } finally {
        // Schedule next poll only after the current response arrives — prevents
        // request pile-up when the API is slower than POLL_INTERVAL_MS.
        if (isMounted) {
          timeoutId = setTimeout(() => { void fetchData() }, POLL_INTERVAL_MS)
        }
      }
    }

    void fetchData()

    return () => {
      isMounted = false
      clearTimeout(timeoutId)
    }
  }, [cameraId])

  const switchCamera = useCallback((id: string) => {
    setCameraId(id)
  }, [])

  return { ...state, cameraId, switchCamera }
}
