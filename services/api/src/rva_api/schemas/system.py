from pydantic import BaseModel

from rva_api.schemas.live import ServiceHealth


class ThroughputPoint(BaseModel):
    time: str
    events: int
    frames: float


class LagPoint(BaseModel):
    time: str
    backlog: int
    lag: int
    api: int


class ContainerStatus(BaseModel):
    name: str
    status: str
    cpu: str
    memory: str
    uptime: str


class VisionRuntimeMetric(BaseModel):
    camera_id: str
    camera_name: str
    processing_fps: float
    detector_fps_target: float
    inference_ms: int
    tracking_ms: int
    zone_ms: int
    reader_queue_size: int
    reader_drop_count: int
    dropped_frames_since_last: int
    gpu_free_ratio: float
    gpu_guard_skipped: int
    stable_track_count: int
    predicted_tracks_count: int
    id_switch_suspect_count: int
    zone_count_total: int


class SystemLogEntry(BaseModel):
    time: str
    level: str
    service: str
    message: str


class PipelineFlowStep(BaseModel):
    name: str
    status: str


class SystemDashboardData(BaseModel):
    generated_at: str
    pipeline_health: list[ServiceHealth]
    throughput: list[ThroughputPoint]
    lag: list[LagPoint]
    vision_runtime: list[VisionRuntimeMetric]
    containers: list[ContainerStatus]
    logs: list[SystemLogEntry]
    flow: list[PipelineFlowStep]
