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
  containers: ContainerStatus[]
  logs: SystemLogEntry[]
  flow: PipelineFlowStep[]
}
