export type AnalyticsTone = 'blue' | 'emerald' | 'amber' | 'violet'

export type AnalyticsKpi = {
  label: string
  value: string
  meta: string
  tone: AnalyticsTone
}

export type HourlyTrafficPoint = {
  hour: string
  visitors: number
  avg_visitors: number
  detections: number
}

export type CameraComparisonPoint = {
  camera_id: string
  detections: number
  share: number
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

export type VisitorsSeriesPoint = {
  label: string
  visitors: number
}

export type WeekdayPatternPoint = {
  weekday: string
  visitors: number
}

export type PeakHeatmapPoint = {
  weekday: string
  weekday_order: number
  hour: number
  visitors: number
}

export type TopZonePoint = {
  zone_id: string
  zone_name: string
  visitors: number
  detections: number
  share: number
  avg_occupancy: number
  occupied_minutes: number
}

export type DwellTrendPoint = {
  date: string
  avg_dwell_sec: number
  p50_dwell_sec: number
  p90_dwell_sec: number
}

export type DailySummaryRow = {
  date: string
  visitors: number
  detections: number
  peak: string
  avg_dwell_sec: number
  avg_confidence: number
  avg_queue_wait_sec: number
  alerts: number
}

export type PeakDaySummary = {
  date: string
  visitors: number
}

export type PeakHourSummary = {
  hour: string
  visitors: number
}

export type AnalyticsDashboardData = {
  generated_at: string
  range_label: string
  data_status: 'ready' | 'empty' | 'error'
  error_message: string | null
  kpis: AnalyticsKpi[]
  total_visitors: number
  peak_day: PeakDaySummary | null
  peak_hour: PeakHourSummary | null
  avg_dwell_sec: number
  hourly_traffic: HourlyTrafficPoint[]
  camera_comparison: CameraComparisonPoint[]
  visitors_over_time: VisitorsSeriesPoint[]
  weekday_pattern: WeekdayPatternPoint[]
  peak_hours_heatmap: PeakHeatmapPoint[]
  top_zones: TopZonePoint[]
  heatmap: HeatmapCell[]
  dwell_bands: DwellBand[]
  dwell_trend: DwellTrendPoint[]
  daily_summary: DailySummaryRow[]
}

export type QueueZoneStat = {
  zone_id: string
  total_sessions: number
  avg_wait_sec: number
  max_wait_sec: number
}

export type QueueWaitTrendPoint = {
  hour: string
  avg_wait_sec: number
  sessions: number
}

export type QueueAnalyticsData = {
  generated_at: string
  range_label: string
  data_status: 'ready' | 'empty' | 'error'
  error_message: string | null
  kpis: AnalyticsKpi[]
  zone_stats: QueueZoneStat[]
  wait_trend: QueueWaitTrendPoint[]
}

export type AlertHistoryRecord = {
  alert_id: string
  camera_id: string
  store_id: string
  alert_type: string
  severity: 'low' | 'medium' | 'high'
  title: string
  description: string
  zone: string
  event_ts: string
  clip_s3_key: string | null
}

export type AlertHistoryData = {
  generated_at: string
  range_label: string
  data_status: 'ready' | 'empty' | 'error'
  error_message: string | null
  records: AlertHistoryRecord[]
}

export type PresenceHeatmapData = {
  generated_at: string
  range_label: string
  camera_id: string
  data_status: 'ready' | 'empty' | 'error'
  error_message: string | null
  grid_rows: number
  grid_cols: number
  cells: HeatmapCell[]
}
