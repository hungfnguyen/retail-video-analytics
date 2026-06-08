from typing import Literal

from pydantic import BaseModel


class AnalyticsKpi(BaseModel):
    label: str
    value: str
    meta: str
    tone: Literal["blue", "emerald", "amber", "violet"]


class HourlyTrafficPoint(BaseModel):
    hour: str
    detections: int
    unique_tracks: int
    average: int


class CameraComparisonPoint(BaseModel):
    camera_id: str
    detections: int
    share: float
    unique_tracks: int
    avg_confidence: float


class HeatmapCell(BaseModel):
    row: int
    col: int
    value: int


class DwellBand(BaseModel):
    label: str
    value: float


class DailySummaryRow(BaseModel):
    date: str
    detections: int
    unique_tracks: int
    peak: str
    avg_dwell_sec: float
    avg_confidence: float


class AnalyticsDashboardData(BaseModel):
    generated_at: str
    range_label: str
    data_status: Literal["ready", "empty", "error"]
    error_message: str | None = None
    kpis: list[AnalyticsKpi]
    hourly_traffic: list[HourlyTrafficPoint]
    camera_comparison: list[CameraComparisonPoint]
    heatmap: list[HeatmapCell]
    dwell_bands: list[DwellBand]
    daily_summary: list[DailySummaryRow]


class QueueZoneStat(BaseModel):
    zone_id: str
    total_sessions: int
    avg_wait_sec: float
    max_wait_sec: float
    unique_visitors: int


class QueueWaitTrendPoint(BaseModel):
    hour: str
    avg_wait_sec: float
    sessions: int


class QueueAnalyticsData(BaseModel):
    generated_at: str
    range_label: str
    data_status: Literal["ready", "empty", "error"]
    error_message: str | None = None
    kpis: list[AnalyticsKpi]
    zone_stats: list[QueueZoneStat]
    wait_trend: list[QueueWaitTrendPoint]


class AlertHistoryRecord(BaseModel):
    alert_id: str
    camera_id: str
    store_id: str
    alert_type: str
    severity: Literal["low", "medium", "high"]
    title: str
    description: str
    zone: str
    event_ts: str
    clip_s3_key: str | None = None


class AlertHistoryData(BaseModel):
    generated_at: str
    range_label: str
    data_status: Literal["ready", "empty", "error"]
    error_message: str | None = None
    records: list[AlertHistoryRecord]
