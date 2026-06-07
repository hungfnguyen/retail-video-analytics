from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, Query

from rva_api.api.v1.analytics_queries import (
    MAX_DAYS,
    alerts_history_sql,
    camera_sql,
    daily_sql,
    hourly_sql,
    queue_wait_trend_sql,
    queue_zone_summary_sql,
    summary_sql,
    trino_query,
)
from rva_api.schemas.analytics import AlertHistoryData, AnalyticsDashboardData, QueueAnalyticsData

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _fmt_duration(seconds: float) -> str:
    if seconds <= 0:
        return "0s"
    minutes = int(seconds // 60)
    remaining = int(seconds % 60)
    if minutes == 0:
        return f"{remaining}s"
    return f"{minutes}m {remaining:02d}s"


def _fmt_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _empty_dashboard(days: int, status: str, message: str | None = None) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "range_label": f"Last {days} days",
        "data_status": status,
        "error_message": message,
        "kpis": [
            {"label": "Total detections", "value": "0", "meta": "No Gold aggregate rows", "tone": "blue"},
            {"label": "Unique tracks", "value": "0", "meta": "Waiting for camera track aggregates", "tone": "emerald"},
            {"label": "Peak hour", "value": "--", "meta": "Waiting for hourly metrics", "tone": "amber"},
            {"label": "Busiest camera", "value": "--", "meta": "No camera rows", "tone": "violet"},
            {"label": "Avg dwell", "value": "0s", "meta": "Waiting for dwell aggregates", "tone": "emerald"},
            {"label": "Avg confidence", "value": "0.0%", "meta": "Waiting for model quality metrics", "tone": "blue"},
        ],
        "hourly_traffic": [],
        "camera_comparison": [],
        "heatmap": [],
        "dwell_bands": [],
        "daily_summary": [],
    }


def _run_dashboard_queries(days: int) -> tuple[dict[str, list[list[Any]]], dict[str, str]]:
    queries = {
        "summary": (summary_sql(days), None),
        "hourly": (hourly_sql(days), None),
        "camera": (camera_sql(days), None),
        "daily": (daily_sql(days), None),
    }
    rows: dict[str, list[list[Any]]] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(trino_query, sql, max_wait): name
            for name, (sql, max_wait) in queries.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                rows[name] = future.result()
            except (HTTPError, URLError, TimeoutError, RuntimeError, OSError) as exc:
                errors[name] = str(exc)
                rows[name] = []

    return rows, errors


@router.get("/alerts", response_model=AlertHistoryData)
def get_alert_history(
    days: int = Query(default=7, ge=1, le=MAX_DAYS),
) -> AlertHistoryData:
    now = datetime.now(timezone.utc)
    try:
        rows = trino_query(alerts_history_sql(days), 10.0)
    except (HTTPError, URLError, TimeoutError, RuntimeError, OSError) as exc:
        return AlertHistoryData.model_validate({
            "generated_at": now.isoformat(),
            "range_label": f"Last {days} days",
            "data_status": "error",
            "error_message": str(exc),
            "records": [],
        })

    if not rows:
        return AlertHistoryData.model_validate({
            "generated_at": now.isoformat(),
            "range_label": f"Last {days} days",
            "data_status": "empty",
            "error_message": None,
            "records": [],
        })

    return AlertHistoryData.model_validate({
        "generated_at": now.isoformat(),
        "range_label": f"Last {days} days",
        "data_status": "ready",
        "error_message": None,
        "records": [
            {
                "alert_id": str(r[0]),
                "camera_id": str(r[1]),
                "store_id": str(r[2]),
                "alert_type": str(r[3]),
                "severity": str(r[4]),
                "title": str(r[5]),
                "description": str(r[6]),
                "zone": str(r[7]),
                "event_ts": str(r[8]),
                "clip_s3_key": r[9] if r[9] else None,
            }
            for r in rows
        ],
    })


@router.get("/queue", response_model=QueueAnalyticsData)
def get_queue_analytics(
    days: int = Query(default=7, ge=1, le=MAX_DAYS),
) -> QueueAnalyticsData:
    now = datetime.now(timezone.utc)
    rows: dict[str, list[list[Any]]] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(trino_query, queue_zone_summary_sql(days), 10.0): "zone_summary",
            executor.submit(trino_query, queue_wait_trend_sql(days), 10.0): "wait_trend",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                rows[name] = future.result()
            except (HTTPError, URLError, TimeoutError, RuntimeError, OSError) as exc:
                errors[name] = str(exc)
                rows[name] = []

    if errors:
        empty_kpis = [
            {"label": "Avg queue wait", "value": "--", "meta": "No data", "tone": "amber"},
            {"label": "Max wait session", "value": "--", "meta": "No data", "tone": "violet"},
            {"label": "Total sessions", "value": "0", "meta": "No data", "tone": "blue"},
        ]
        return QueueAnalyticsData.model_validate({
            "generated_at": now.isoformat(),
            "range_label": f"Last {days} days",
            "data_status": "error",
            "error_message": "; ".join(errors.values()),
            "kpis": empty_kpis,
            "zone_stats": [],
            "wait_trend": [],
        })

    zone_rows = rows["zone_summary"]
    trend_rows = rows["wait_trend"]

    if not zone_rows:
        return QueueAnalyticsData.model_validate({
            "generated_at": now.isoformat(),
            "range_label": f"Last {days} days",
            "data_status": "empty",
            "error_message": None,
            "kpis": [
                {"label": "Avg queue wait", "value": "0s", "meta": "No queue sessions yet", "tone": "amber"},
                {"label": "Max wait session", "value": "0s", "meta": "No queue sessions yet", "tone": "violet"},
                {"label": "Total sessions", "value": "0", "meta": "No queue sessions yet", "tone": "blue"},
            ],
            "zone_stats": [],
            "wait_trend": [],
        })

    total_sessions = sum(_safe_int(r[1]) for r in zone_rows)
    overall_avg_wait = sum(_safe_float(r[2]) * _safe_int(r[1]) for r in zone_rows) / total_sessions if total_sessions else 0.0
    max_wait = max((_safe_float(r[3]) for r in zone_rows), default=0.0)
    busiest_zone = zone_rows[0][0] if zone_rows else "--"

    return QueueAnalyticsData.model_validate({
        "generated_at": now.isoformat(),
        "range_label": f"Last {days} days",
        "data_status": "ready",
        "error_message": None,
        "kpis": [
            {
                "label": "Avg queue wait",
                "value": _fmt_duration(overall_avg_wait),
                "meta": f"across {len(zone_rows)} zone(s)",
                "tone": "amber",
            },
            {
                "label": "Max wait session",
                "value": _fmt_duration(max_wait),
                "meta": f"slowest zone: {busiest_zone.replace('_', ' ')}",
                "tone": "violet",
            },
            {
                "label": "Total sessions",
                "value": _fmt_int(total_sessions),
                "meta": f"last {days} days",
                "tone": "blue",
            },
        ],
        "zone_stats": [
            {
                "zone_id": str(r[0]),
                "total_sessions": _safe_int(r[1]),
                "avg_wait_sec": _safe_float(r[2]),
                "max_wait_sec": _safe_float(r[3]),
                "unique_visitors": _safe_int(r[4]),
            }
            for r in zone_rows
        ],
        "wait_trend": [
            {
                "hour": str(r[0]),
                "avg_wait_sec": _safe_float(r[1]),
                "sessions": _safe_int(r[2]),
            }
            for r in trend_rows
        ],
    })


@router.get("/dashboard", response_model=AnalyticsDashboardData)
def get_analytics_dashboard(
    days: int = Query(default=7, ge=1, le=MAX_DAYS),
) -> AnalyticsDashboardData:
    rows, errors = _run_dashboard_queries(days)
    if errors:
        return AnalyticsDashboardData.model_validate(
            _empty_dashboard(days, "error", "; ".join(errors.values()))
        )

    summary_row = rows["summary"][0] if rows["summary"] else []
    hourly_rows = rows["hourly"]
    camera_rows = rows["camera"]
    daily_rows = rows["daily"]

    total_detections = _safe_int(summary_row[0] if len(summary_row) > 0 else 0)
    if total_detections == 0:
        return AnalyticsDashboardData.model_validate(_empty_dashboard(days, "empty"))

    unique_tracks = _safe_int(summary_row[1] if len(summary_row) > 1 else 0)
    active_days = _safe_int(summary_row[2] if len(summary_row) > 2 else 0)
    avg_conf = _safe_float(summary_row[3] if len(summary_row) > 3 else 0.0)
    avg_per_active_day = _safe_float(summary_row[4] if len(summary_row) > 4 else 0.0)
    avg_dwell_sec = _safe_float(summary_row[5] if len(summary_row) > 5 else 0.0)
    track_count = _safe_int(summary_row[6] if len(summary_row) > 6 else 0)
    long_dwell_tracks = _safe_int(summary_row[7] if len(summary_row) > 7 else 0)
    short_dwell_tracks = _safe_int(summary_row[8] if len(summary_row) > 8 else 0)

    peak_row = max(hourly_rows, key=lambda row: _safe_int(row[1])) if hourly_rows else ["--", 0, 0, 0]
    busiest_camera = camera_rows[0] if camera_rows else ["--", 0, 0, 0, 0]

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "range_label": f"Last {days} days",
        "data_status": "ready",
        "error_message": None,
        "kpis": [
            {
                "label": "Total detections",
                "value": _fmt_int(total_detections),
                "meta": f"{active_days} active days, {_fmt_int(round(avg_per_active_day))}/active day",
                "tone": "blue",
            },
            {
                "label": "Unique tracks",
                "value": _fmt_int(unique_tracks),
                "meta": "Camera-scoped visit tracks",
                "tone": "emerald",
            },
            {
                "label": "Peak hour",
                "value": str(peak_row[0]),
                "meta": f"{_fmt_int(_safe_int(peak_row[1]))} detections",
                "tone": "amber",
            },
            {
                "label": "Busiest camera",
                "value": str(busiest_camera[0]),
                "meta": f"{_fmt_int(_safe_int(busiest_camera[1]))} detections",
                "tone": "violet",
            },
            {
                "label": "Avg dwell",
                "value": _fmt_duration(avg_dwell_sec),
                "meta": f"{_fmt_int(track_count)} tracks, {_fmt_int(long_dwell_tracks)} long dwell",
                "tone": "emerald",
            },
            {
                "label": "Avg confidence",
                "value": _fmt_percent(avg_conf),
                "meta": f"{_fmt_int(short_dwell_tracks)} short dwell tracks",
                "tone": "blue",
            },
        ],
        "hourly_traffic": [
            {
                "hour": str(row[0]),
                "detections": _safe_int(row[1]),
                "unique_tracks": _safe_int(row[2]),
                "average": _safe_int(row[3]),
            }
            for row in hourly_rows
        ],
        "camera_comparison": [
            {
                "camera_id": str(row[0]),
                "detections": _safe_int(row[1]),
                "share": _safe_float(row[2]),
                "unique_tracks": _safe_int(row[3]),
                "avg_confidence": _safe_float(row[4]),
            }
            for row in camera_rows
        ],
        "heatmap": [],
        "dwell_bands": [],
        "daily_summary": [
            {
                "date": str(row[0]),
                "detections": _safe_int(row[1]),
                "unique_tracks": _safe_int(row[2]),
                "peak": str(row[3]),
                "avg_dwell_sec": round(_safe_float(row[4]), 1),
                "avg_confidence": round(_safe_float(row[5]), 4),
            }
            for row in daily_rows
        ],
    }
    return AnalyticsDashboardData.model_validate(data)
