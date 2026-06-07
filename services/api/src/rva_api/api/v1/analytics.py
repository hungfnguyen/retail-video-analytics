from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, Query

from rva_api.api.v1.analytics_queries import (
    MAX_DAYS,
    avg_dwell_sql,
    camera_sql,
    daily_sql,
    dwell_sql,
    heatmap_sql,
    hourly_sql,
    queue_wait_trend_sql,
    queue_zone_summary_sql,
    trino_query,
)
from rva_api.schemas.analytics import AnalyticsDashboardData, QueueAnalyticsData

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


def _empty_dashboard(days: int, status: str, message: str | None = None) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "range_label": f"Last {days} days",
        "data_status": status,
        "error_message": message,
        "kpis": [
            {"label": "Total detections", "value": "0", "meta": "No lakehouse rows", "tone": "blue"},
            {"label": "Peak hour", "value": "--", "meta": "Waiting for Silver data", "tone": "amber"},
            {"label": "Busiest camera", "value": "--", "meta": "No camera rows", "tone": "violet"},
            {"label": "Avg dwell", "value": "0s", "meta": "Waiting for Gold data", "tone": "emerald"},
        ],
        "hourly_traffic": [],
        "camera_comparison": [],
        "heatmap": [],
        "dwell_bands": [],
        "daily_summary": [],
    }


def _run_dashboard_queries(days: int) -> tuple[dict[str, list[list[Any]]], dict[str, str]]:
    queries = {
        "hourly": (hourly_sql(days), None),
        "camera": (camera_sql(days), None),
        "heatmap": (heatmap_sql(days), None),
        "daily": (daily_sql(days), None),
        "dwell": (dwell_sql(days), 5.0),
        "avg_dwell": (avg_dwell_sql(days), 5.0),
    }
    rows: dict[str, list[list[Any]]] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=2) as executor:
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
    required_errors = {
        name: errors[name]
        for name in ("hourly", "camera", "heatmap", "daily")
        if name in errors
    }
    if required_errors:
        return AnalyticsDashboardData.model_validate(
            _empty_dashboard(days, "error", "; ".join(required_errors.values()))
        )

    hourly_rows = rows["hourly"]
    camera_rows = rows["camera"]
    heatmap_rows = rows["heatmap"]
    dwell_rows = rows["dwell"]
    daily_rows = rows["daily"]
    avg_dwell_rows = rows["avg_dwell"]

    total_detections = sum(_safe_int(row[1]) for row in hourly_rows)
    if total_detections == 0:
        return AnalyticsDashboardData.model_validate(_empty_dashboard(days, "empty"))

    peak_row = max(hourly_rows, key=lambda row: _safe_int(row[1]))
    busiest_camera = camera_rows[0] if camera_rows else ["--", 0, 0]
    avg_dwell_sec = _safe_float(avg_dwell_rows[0][0]) if avg_dwell_rows else 0.0
    track_count = _safe_int(avg_dwell_rows[0][1]) if avg_dwell_rows else 0
    dwell_total = sum(_safe_int(row[1]) for row in dwell_rows)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "range_label": f"Last {days} days",
        "data_status": "ready",
        "error_message": None,
        "kpis": [
            {
                "label": "Total detections",
                "value": _fmt_int(total_detections),
                "meta": f"{len(daily_rows)} active days in lakehouse",
                "tone": "blue",
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
                "meta": f"{_fmt_int(track_count)} tracks in Gold",
                "tone": "emerald",
            },
        ],
        "hourly_traffic": [
            {
                "hour": str(row[0]),
                "detections": _safe_int(row[1]),
                "average": round(_safe_int(row[1]) / days),
            }
            for row in hourly_rows
        ],
        "camera_comparison": [
            {
                "camera_id": str(row[0]),
                "detections": _safe_int(row[1]),
                "share": _safe_float(row[2]),
            }
            for row in camera_rows
        ],
        "heatmap": [
            {"row": _safe_int(row[0]), "col": _safe_int(row[1]), "value": _safe_int(row[2])}
            for row in heatmap_rows
        ],
        "dwell_bands": [
            {
                "label": str(row[0]),
                "value": round((_safe_int(row[1]) * 100.0 / dwell_total), 1) if dwell_total else 0.0,
            }
            for row in dwell_rows
        ],
        "daily_summary": [
            {
                "date": str(row[0]),
                "detections": _safe_int(row[1]),
                "peak": str(row[2]),
                "avg_dwell_sec": round(_safe_float(row[3]), 1),
            }
            for row in daily_rows
        ],
    }
    return AnalyticsDashboardData.model_validate(data)
