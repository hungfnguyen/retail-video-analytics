import type { AnalyticsDashboardData } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const REQUEST_TIMEOUT_MS = 60_000

export async function getAnalyticsDashboardData(days = 7): Promise<AnalyticsDashboardData> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  const response = await fetch(`${API_BASE_URL}/api/v1/analytics/dashboard?days=${encodeURIComponent(days)}`, {
    signal: controller.signal,
  }).finally(() => {
    window.clearTimeout(timeoutId)
  })

  if (!response.ok) {
    throw new Error('Failed to fetch analytics dashboard data.')
  }

  return response.json()
}
