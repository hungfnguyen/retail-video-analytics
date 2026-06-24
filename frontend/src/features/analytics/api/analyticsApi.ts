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

function analyticsUrl(path: string, days: number, cameraId?: string | null): string {
  const params = new URLSearchParams({ days: String(days) })
  if (cameraId) params.set('camera_id', cameraId)
  return `${API_BASE_URL}/api/v1/analytics/${path}?${params.toString()}`
}

export function getAnalyticsDashboardData(days = 7, cameraId?: string | null): Promise<AnalyticsDashboardData> {
  return fetchJson(analyticsUrl('dashboard', days, cameraId))
}

export function getQueueAnalyticsData(days = 7, cameraId?: string | null): Promise<QueueAnalyticsData> {
  return fetchJson(analyticsUrl('queue', days, cameraId))
}

export function getAlertHistoryData(days = 7, cameraId?: string | null): Promise<AlertHistoryData> {
  return fetchJson(analyticsUrl('alerts', days, cameraId))
}

export function getPresenceHeatmapData(cameraId: string, days = 7): Promise<PresenceHeatmapData> {
  return fetchJson(
    `${API_BASE_URL}/api/v1/analytics/heatmap?camera_id=${encodeURIComponent(cameraId)}&days=${days}&metric=presence`,
  )
}
