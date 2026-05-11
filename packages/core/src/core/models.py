"""Pydantic models for event contracts shared across services."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class BBoxNorm(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Centroid(BaseModel):
    x: int
    y: int


class CentroidNorm(BaseModel):
    x: float
    y: float


class ImageSize(BaseModel):
    width: int
    height: int


class Source(BaseModel):
    store_id: str
    camera_id: str
    stream_id: str


class Runtime(BaseModel):
    model_name: str
    tracker_type: str
    conf_thres: float | None = None
    class_filter: list[int] | None = None


class DetectionObject(BaseModel):
    det_id: str
    class_name: str = Field(alias="class")
    class_id: int
    conf: float
    bbox: BBox
    bbox_norm: BBoxNorm
    centroid: Centroid
    centroid_norm: CentroidNorm
    track_id: int | None = None

    model_config = {"populate_by_name": True}


class DetectionFrameEvent(BaseModel):
    schema_version: str = "1.0"
    pipeline_run_id: str
    source: Source
    frame_index: int
    capture_ts: str
    image_size: ImageSize
    detections: list[DetectionObject]
    runtime: Runtime | None = None
    source_uri: str | None = None

    def to_pulsar_payload(self) -> bytes:
        return self.model_dump_json(by_alias=True).encode("utf-8")


class SampledFrameResult(BaseModel):
    schema_version: str = "1.0"
    event_type: str = "sampled_frame_created"
    pipeline_run_id: str
    source: dict[str, Any]
    frame_index: int
    capture_ts: str
    upload_ts: str
    image_size: dict[str, int]
    bucket: str
    s3_key: str
    s3_uri: str
    content_type: str = "image/jpeg"
    byte_size: int
    jpeg_quality: int


class ClipCreatedResult(BaseModel):
    schema_version: str = "1.0"
    event_type: str = "clip_created"
    pipeline_run_id: str
    alert_id: str
    alert_type: str
    source: dict[str, Any]
    trigger_frame_index: int
    trigger_ts: str
    upload_ts: str
    bucket: str
    clip_s3_key: str
    clip_s3_uri: str
    content_type: str = "video/mp4"
    clip_duration_sec: float
    frame_count: int
    byte_size: int


class TrackLifecycleEvent(BaseModel):
    schema_version: str = "1.0"
    event_type: str  # "track_started", "track_ended", "track_sample"
    pipeline_run_id: str
    source: Source
    track_id: int
    event_ts: str
    bbox: BBox | None = None
    centroid: Centroid | None = None
    confidence: float | None = None
    frame_uri: str | None = None


class AlertEvent(BaseModel):
    schema_version: str = "1.0"
    event_type: str = "density_alert"
    alert_id: str
    pipeline_run_id: str
    source: Source
    alert_type: str
    trigger_frame_index: int
    trigger_ts: str
    current_count: int
    threshold: int
    message: str | None = None
