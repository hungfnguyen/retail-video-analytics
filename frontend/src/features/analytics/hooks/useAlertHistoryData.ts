import { useCallback, useEffect, useState } from 'react'
import { getAlertHistoryData } from '../api/analyticsApi'
import type { AlertHistoryData } from '../types'

const POLL_INTERVAL_MS = 60_000

type State = { data: AlertHistoryData | null; error: string | null }

export function useAlertHistoryData(days: number) {
  const [state, setState] = useState<State>({ data: null, error: null })

  const refresh = useCallback(async () => {
    try {
      const data = await getAlertHistoryData(days)
      setState({ data, error: null })
    } catch {
      setState({ data: null, error: 'Unable to load alert history.' })
    }
  }, [days])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => { void refresh() }, POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  return { ...state, refresh }
}
