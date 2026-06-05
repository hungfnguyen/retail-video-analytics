export type Store = {
  store_id: string
  name: string
  location: string
}

export type Camera = {
  camera_id: string
  store_id: string
  name: string
  zone: string
  source_type: 'video_file' | 'rtsp' | 'webcam'
  status: 'online' | 'offline' | 'warning'
}

export type Detection = {
  track_id: number
  global_track_id?: string | null
  label: 'person'
  confidence: number
  bbox_norm: {
    x: number
    y: number
    w: number
    h: number
  }
}

export type HeatmapPoint = {
  x: number
  y: number
  intensity: number
}

export type ZoneCount = {
  zone_id: string
  zone_name?: string | null
  zone_type: string
  count: number
  track_ids?: number[]
  global_track_ids?: string[]
}

export type LineCrossing = {
  line_id: string
  line_type: string
  direction: string
  track_id?: number | null
  global_track_id?: string | null
}

export type LiveFrame = {
  camera_id: string
  frame_id: number
  capture_ts: string
  image_url: string
  image_size: {
    width: number
    height: number
  }
  fps: number
  latency_ms: number
  media_fps: number
  media_latency_ms: number
  metadata_latency_ms: number
  metadata_status: 'fresh' | 'lagging' | 'stale' | 'missing'
  media_status: 'online' | 'warning' | 'missing'
  processing_fps: number
  inference_ms: number
  postprocess_ms: number
  draw_ms: number
  encode_ms: number
  jpeg_size_bytes: number
  reader_queue_size: number
  reader_drop_count: number
  detections: Detection[]
  heatmap_points: HeatmapPoint[]
  zone_counts: ZoneCount[]
  line_crossings: LineCrossing[]
}

export type LiveStats = {
  camera_id: string
  current_count: number
  count_source: 'camera_realtime' | 'redis' | 'live_frame_fallback' | 'missing'
  active_tracks: number
  fps: number
  latency_ms: number
  media_fps: number
  media_latency_ms: number
  metadata_latency_ms: number
  metadata_status: 'fresh' | 'lagging' | 'stale' | 'missing'
  count_change_percent: number
  tracks_change_percent: number
  status: 'stable' | 'warning' | 'critical'
  updated_at: string
}

export type Alert = {
  alert_id: string
  store_id?: string
  camera_id: string
  alert_type?: string
  title: string
  description: string
  severity: 'low' | 'medium' | 'high'
  zone: string
  track_id?: number
  event_ts: string
  status: 'new' | 'acknowledged' | 'resolved'
  trigger_value?: number
  threshold?: number
  clip_s3_key?: string
  clip_s3_uri?: string
}

export type TrafficPoint = {
  time: string
  people_in: number
  people_out: number
  current_count: number
}

export type TrafficSummary = {
  total_in: number
  total_out: number
  current_total: number
  peak_count: number
  peak_time: string
}

export type ZoneHeatmapCell = {
  zone_row: string
  zone_col: number
  value: number
}

export type ServiceHealth = {
  service: 'pulsar' | 'flink' | 'redis' | 's3' | 'trino' | 'fastapi'
  display_name: string
  role: string
  status: 'ok' | 'warning' | 'down'
  last_check_ts: string
  latency_ms: number
}

export type LiveDashboardData = {
  store: Store
  cameras: Camera[]
  selected_camera_id: string
  frame: LiveFrame
  stats: LiveStats
  alerts: Alert[]
  traffic: TrafficPoint[]
  traffic_summary: TrafficSummary
  zone_heatmap: ZoneHeatmapCell[]
  pipeline_health: ServiceHealth[]
}
