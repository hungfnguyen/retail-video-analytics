import type { LiveDashboardData } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function getLiveDashboardData(cameraId = 'cam_01'): Promise<LiveDashboardData> {
  const response = await fetch(`${API_BASE_URL}/api/v1/live/${encodeURIComponent(cameraId)}/dashboard`)

  if (!response.ok) {
    throw new Error('Failed to fetch live dashboard data.')
  }

  return response.json()
}
