import type { ServiceHealth } from '../live/types'

export type ThroughputPoint = {
  time: string
  events: number
  frames: number
}

export type LagPoint = {
  time: string
  backlog: number
  lag: number
  api: number
}
export type VisionRuntimeMetric = {
  camera_id: string
  camera_name: string
  processing_fps: number
  detector_fps_target: number
  inference_ms: number
  tracking_ms: number
  zone_ms: number
  reader_queue_size: number
  reader_drop_count: number
  dropped_frames_since_last: number
  gpu_free_ratio: number
  gpu_guard_skipped: number
  stable_track_count: number
  predicted_tracks_count: number
  id_switch_suspect_count: number
  zone_count_total: number
}

export type ContainerStatus = {
  name: string
  status: string
  cpu: string
  memory: string
  uptime: string
}

export type SystemLogEntry = {
  time: string
  level: string
  service: string
  message: string
}

export type PipelineFlowStep = {
  name: string
  status: 'ok' | 'warning' | 'down' | string
}

export type SystemDashboardData = {
  generated_at: string
  pipeline_health: ServiceHealth[]
  throughput: ThroughputPoint[]
  lag: LagPoint[]
  vision_runtime: VisionRuntimeMetric[]
  containers: ContainerStatus[]
  logs: SystemLogEntry[]
  flow: PipelineFlowStep[]
}
