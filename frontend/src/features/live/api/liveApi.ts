import { liveDashboardMock } from '../mocks/liveMock'
import type { LiveDashboardData } from '../types'

export async function getLiveDashboardData(): Promise<LiveDashboardData> {
  return liveDashboardMock
}
