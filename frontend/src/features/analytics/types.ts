export type AnalyticsTone = 'blue' | 'emerald' | 'amber' | 'violet'

export type AnalyticsKpi = {
  label: string
  value: string
  meta: string
  tone: AnalyticsTone
}

export type HourlyTrafficPoint = {
  hour: string
  detections: number
  unique_tracks: number
  average: number
}

export type CameraComparisonPoint = {
  camera_id: string
  detections: number
  share: number
  unique_tracks: number
  avg_confidence: number
}

export type HeatmapCell = {
  row: number
  col: number
  value: number
}

export type DwellBand = {
  label: string
  value: number
}

export type DailySummaryRow = {
  date: string
  detections: number
  unique_tracks: number
  peak: string
  avg_dwell_sec: number
  avg_confidence: number
}

export type AnalyticsDashboardData = {
  generated_at: string
  range_label: string
  data_status: 'ready' | 'empty' | 'error'
  error_message: string | null
  kpis: AnalyticsKpi[]
  hourly_traffic: HourlyTrafficPoint[]
  camera_comparison: CameraComparisonPoint[]
  heatmap: HeatmapCell[]
  dwell_bands: DwellBand[]
  daily_summary: DailySummaryRow[]
}
