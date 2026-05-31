import type { SystemDashboardData } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function getSystemDashboardData(cameraId = 'cam_01'): Promise<SystemDashboardData> {
  const response = await fetch(`${API_BASE_URL}/api/v1/system/dashboard?camera_id=${encodeURIComponent(cameraId)}`)

  if (!response.ok) {
    throw new Error('Failed to fetch system dashboard data.')
  }

  return response.json()
}
