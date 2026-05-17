import { useEffect, useState } from 'react'
import { getLiveDashboardData } from '../api/liveApi'
import type { LiveDashboardData } from '../types'

type LiveDataState = {
  data: LiveDashboardData | null
  error: string | null
}

export function useLiveData() {
  const [state, setState] = useState<LiveDataState>({
    data: null,
    error: null,
  })

  useEffect(() => {
    let isMounted = true

    getLiveDashboardData()
      .then((data) => {
        if (isMounted) {
          setState({ data, error: null })
        }
      })
      .catch(() => {
        if (isMounted) {
          setState({ data: null, error: 'Unable to load live dashboard data.' })
        }
      })

    return () => {
      isMounted = false
    }
  }, [])

  return state
}
