import type { AlertHistoryData, AnalyticsDashboardData, PresenceHeatmapData, QueueAnalyticsData } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const REQUEST_TIMEOUT_MS = 60_000

async function fetchJson<T>(url: string): Promise<T> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  const response = await fetch(url, { signal: controller.signal }).finally(() => {
    window.clearTimeout(timeoutId)
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

export function getAnalyticsDashboardData(days = 7): Promise<AnalyticsDashboardData> {
  return fetchJson(`${API_BASE_URL}/api/v1/analytics/dashboard?days=${encodeURIComponent(days)}`)
}

export function getQueueAnalyticsData(days = 7): Promise<QueueAnalyticsData> {
  return fetchJson(`${API_BASE_URL}/api/v1/analytics/queue?days=${encodeURIComponent(days)}`)
}

export function getAlertHistoryData(days = 7): Promise<AlertHistoryData> {
  return fetchJson(`${API_BASE_URL}/api/v1/analytics/alerts?days=${encodeURIComponent(days)}`)
}

export function getPresenceHeatmapData(cameraId: string, days = 7): Promise<PresenceHeatmapData> {
  return fetchJson(
    `${API_BASE_URL}/api/v1/analytics/heatmap?camera_id=${encodeURIComponent(cameraId)}&days=${days}&metric=presence`,
  )
}
