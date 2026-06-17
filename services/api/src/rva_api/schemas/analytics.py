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
    average: int


class CameraComparisonPoint(BaseModel):
    camera_id: str
    detections: int
    share: float
    avg_confidence: float


class HeatmapCell(BaseModel):
    row: int
    col: int
    value: int


class DwellBand(BaseModel):
    label: str
    value: float


class VisitorsSeriesPoint(BaseModel):
    label: str
    visitors: int


class WeekdayPatternPoint(BaseModel):
    weekday: str
    visitors: int


class PeakHeatmapPoint(BaseModel):
    weekday: str
    weekday_order: int
    hour: int
    visitors: int


class TopZonePoint(BaseModel):
    zone_id: str
    zone_name: str
    visitors: int
    share: float
    avg_occupancy: float
    occupied_minutes: int


class DwellTrendPoint(BaseModel):
    date: str
    avg_dwell_sec: float
    p50_dwell_sec: float
    p90_dwell_sec: float


class DailySummaryRow(BaseModel):
    date: str
    detections: int
    peak: str
    avg_dwell_sec: float
    avg_confidence: float
    avg_queue_wait_sec: float = 0
    alerts: int = 0


class PeakDaySummary(BaseModel):
    date: str
    visitors: int


class PeakHourSummary(BaseModel):
    hour: str
    visitors: int


class AnalyticsDashboardData(BaseModel):
    generated_at: str
    range_label: str
    data_status: Literal["ready", "empty", "error"]
    error_message: str | None = None
    kpis: list[AnalyticsKpi]
    total_visitors: int = 0
    peak_day: PeakDaySummary | None = None
    peak_hour: PeakHourSummary | None = None
    avg_dwell_sec: float = 0
    hourly_traffic: list[HourlyTrafficPoint]
    camera_comparison: list[CameraComparisonPoint]
    visitors_over_time: list[VisitorsSeriesPoint] = []
    weekday_pattern: list[WeekdayPatternPoint] = []
    peak_hours_heatmap: list[PeakHeatmapPoint] = []
    top_zones: list[TopZonePoint] = []
    heatmap: list[HeatmapCell]
    dwell_bands: list[DwellBand]
    dwell_trend: list[DwellTrendPoint] = []
    daily_summary: list[DailySummaryRow]


class QueueZoneStat(BaseModel):
    zone_id: str
    total_sessions: int
    avg_wait_sec: float
    max_wait_sec: float


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


class PresenceHeatmapData(BaseModel):
    generated_at: str
    range_label: str
    camera_id: str
    data_status: Literal["ready", "empty", "error"]
    error_message: str | None = None
    grid_rows: int
    grid_cols: int
    cells: list[HeatmapCell]
