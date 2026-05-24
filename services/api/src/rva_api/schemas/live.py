from typing import Literal

from pydantic import BaseModel


class Store(BaseModel):
    store_id: str
    name: str
    location: str


class Camera(BaseModel):
    camera_id: str
    store_id: str
    name: str
    zone: str
    source_type: Literal["video_file", "rtsp", "webcam"]
    status: Literal["online", "offline", "warning"]


class BboxNorm(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Detection(BaseModel):
    track_id: int
    label: Literal["person"]
    confidence: float
    bbox_norm: BboxNorm


class HeatmapPoint(BaseModel):
    x: float
    y: float
    intensity: float


class ImageSize(BaseModel):
    width: int
    height: int


class LiveFrame(BaseModel):
    camera_id: str
    frame_id: int
    capture_ts: str
    image_url: str
    image_size: ImageSize
    fps: float
    latency_ms: int
    media_fps: float
    media_latency_ms: int
    metadata_latency_ms: int
    metadata_status: Literal["fresh", "lagging", "stale", "missing"]
    media_status: Literal["online", "warning", "missing"]
    processing_fps: float
    inference_ms: int
    postprocess_ms: int
    draw_ms: int
    encode_ms: int
    jpeg_size_bytes: int
    reader_queue_size: int
    reader_drop_count: int
    detections: list[Detection]
    heatmap_points: list[HeatmapPoint]


class LiveStats(BaseModel):
    camera_id: str
    current_count: int
    count_source: Literal["camera_realtime", "redis", "live_frame_fallback", "missing"]
    active_tracks: int
    fps: float
    latency_ms: int
    media_fps: float
    media_latency_ms: int
    metadata_latency_ms: int
    metadata_status: Literal["fresh", "lagging", "stale", "missing"]
    count_change_percent: int
    tracks_change_percent: int
    status: Literal["stable", "warning", "critical"]
    updated_at: str


class Alert(BaseModel):
    alert_id: str
    camera_id: str
    title: str
    description: str
    severity: Literal["low", "medium", "high"]
    zone: str
    track_id: int | None = None
    event_ts: str
    status: Literal["new", "acknowledged", "resolved"]


class TrafficPoint(BaseModel):
    time: str
    people_in: int
    people_out: int
    current_count: int


class TrafficSummary(BaseModel):
    total_in: int
    total_out: int
    current_total: int
    peak_count: int
    peak_time: str


class ZoneHeatmapCell(BaseModel):
    zone_row: str
    zone_col: int
    value: int


class ServiceHealth(BaseModel):
    service: Literal["pulsar", "flink", "redis", "minio", "trino", "fastapi"]
    display_name: str
    role: str
    status: Literal["ok", "warning", "down"]
    last_check_ts: str
    latency_ms: int


class LiveDashboardData(BaseModel):
    store: Store
    cameras: list[Camera]
    selected_camera_id: str
    frame: LiveFrame
    stats: LiveStats
    alerts: list[Alert]
    traffic: list[TrafficPoint]
    traffic_summary: TrafficSummary
    zone_heatmap: list[ZoneHeatmapCell]
    pipeline_health: list[ServiceHealth]
