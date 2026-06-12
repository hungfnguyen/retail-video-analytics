from __future__ import annotations

import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, HTTPException, Query

from rva_api.api.v1.analytics_queries import (
    MAX_DAYS,
    alerts_history_sql,
    camera_sql,
    daily_sql,
    heatmap_presence_sql,
    hourly_sql,
    queue_wait_trend_sql,
    queue_zone_summary_sql,
    summary_sql,
    trino_query,
)
from rva_api.schemas.analytics import AlertHistoryData, AnalyticsDashboardData, PresenceHeatmapData, QueueAnalyticsData
from storage import RedisClientConfig, create_redis_client

router = APIRouter(prefix="/analytics", tags=["analytics"])

_analytics_cache_client: Any | None = None
_analytics_cache_disabled = False

DASHBOARD_CACHE_TTL_SEC = int(os.getenv("ANALYTICS_DASHBOARD_CACHE_TTL_SEC", "120"))
QUEUE_CACHE_TTL_SEC = int(os.getenv("ANALYTICS_QUEUE_CACHE_TTL_SEC", "120"))
HEATMAP_CACHE_TTL_1D_SEC = int(os.getenv("ANALYTICS_HEATMAP_CACHE_TTL_1D_SEC", "300"))
HEATMAP_CACHE_TTL_LONG_SEC = int(os.getenv("ANALYTICS_HEATMAP_CACHE_TTL_LONG_SEC", "900"))
ALERTS_CACHE_TTL_SEC = int(os.getenv("ANALYTICS_ALERTS_CACHE_TTL_SEC", "300"))
EMPTY_RESULT_CACHE_TTL_SEC = int(os.getenv("ANALYTICS_EMPTY_CACHE_TTL_SEC", "60"))


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


_CAMERA_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_camera_id(camera_id: str) -> None:
    if not _CAMERA_ID_RE.fullmatch(camera_id):
        raise HTTPException(status_code=400, detail="Invalid camera_id")


def _cache_config() -> RedisClientConfig:
    return RedisClientConfig(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", os.getenv("REDIS_HOST_PORT", "16379"))),
        password=os.getenv("REDIS_PASSWORD") or None,
        db=int(os.getenv("REDIS_DB", "0")),
    )


def _get_cache_client() -> Any | None:
    global _analytics_cache_client, _analytics_cache_disabled

    if _analytics_cache_client is not None:
        return _analytics_cache_client
    if _analytics_cache_disabled:
        return None

    _analytics_cache_client = create_redis_client(_cache_config())
    if _analytics_cache_client is None:
        _analytics_cache_disabled = True
        return None
    return _analytics_cache_client


def _cache_key(name: str, *parts: str) -> str:
    normalized = [part.replace(" ", "_") for part in parts]
    return ":".join(["analytics", "cache", "v1", name, *normalized])


def _cache_get(model_cls: type[Any], key: str) -> Any | None:
    client = _get_cache_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
    except Exception:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return model_cls.model_validate(payload)
    except Exception:
        return None


def _cache_set(key: str, payload: dict[str, Any], ttl_sec: int) -> None:
    client = _get_cache_client()
    if client is None or ttl_sec <= 0:
        return
    try:
        client.setex(key, ttl_sec, json.dumps(payload, separators=(",", ":")))
    except Exception:
        return


def _cacheable_status(payload: dict[str, Any]) -> str | None:
    status = payload.get("data_status")
    if status in {"ready", "empty"}:
        return str(status)
    return None


def _cache_ttl_for_status(ready_ttl_sec: int, status: str) -> int:
    if status == "empty":
        return min(ready_ttl_sec, EMPTY_RESULT_CACHE_TTL_SEC)
    return ready_ttl_sec


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
    cache_key = _cache_key("alerts", f"days_{days}")
    cached = _cache_get(AlertHistoryData, cache_key)
    if cached is not None:
        return cached

    now = datetime.now(timezone.utc)
    try:
        rows = trino_query(alerts_history_sql(days), 10.0)
    except (HTTPError, URLError, TimeoutError, RuntimeError, OSError) as exc:
        payload = {
            "generated_at": now.isoformat(),
            "range_label": f"Last {days} days",
            "data_status": "error",
            "error_message": str(exc),
            "records": [],
        }
        return AlertHistoryData.model_validate(payload)

    if not rows:
        payload = {
            "generated_at": now.isoformat(),
            "range_label": f"Last {days} days",
            "data_status": "empty",
            "error_message": None,
            "records": [],
        }
        _cache_set(cache_key, payload, _cache_ttl_for_status(ALERTS_CACHE_TTL_SEC, "empty"))
        return AlertHistoryData.model_validate(payload)

    payload = {
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
    }
    _cache_set(cache_key, payload, _cache_ttl_for_status(ALERTS_CACHE_TTL_SEC, "ready"))
    return AlertHistoryData.model_validate(payload)


@router.get("/queue", response_model=QueueAnalyticsData)
def get_queue_analytics(
    days: int = Query(default=7, ge=1, le=MAX_DAYS),
) -> QueueAnalyticsData:
    cache_key = _cache_key("queue", f"days_{days}")
    cached = _cache_get(QueueAnalyticsData, cache_key)
    if cached is not None:
        return cached

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
        payload = {
            "generated_at": now.isoformat(),
            "range_label": f"Last {days} days",
            "data_status": "error",
            "error_message": "; ".join(errors.values()),
            "kpis": empty_kpis,
            "zone_stats": [],
            "wait_trend": [],
        }
        return QueueAnalyticsData.model_validate(payload)

    zone_rows = rows["zone_summary"]
    trend_rows = rows["wait_trend"]

    if not zone_rows:
        payload = {
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
        }
        _cache_set(cache_key, payload, _cache_ttl_for_status(QUEUE_CACHE_TTL_SEC, "empty"))
        return QueueAnalyticsData.model_validate(payload)

    total_sessions = sum(_safe_int(r[1]) for r in zone_rows)
    overall_avg_wait = sum(_safe_float(r[2]) * _safe_int(r[1]) for r in zone_rows) / total_sessions if total_sessions else 0.0
    max_wait = max((_safe_float(r[3]) for r in zone_rows), default=0.0)
    busiest_zone = zone_rows[0][0] if zone_rows else "--"

    payload = {
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
    }
    _cache_set(cache_key, payload, _cache_ttl_for_status(QUEUE_CACHE_TTL_SEC, "ready"))
    return QueueAnalyticsData.model_validate(payload)


@router.get("/dashboard", response_model=AnalyticsDashboardData)
def get_analytics_dashboard(
    days: int = Query(default=7, ge=1, le=MAX_DAYS),
) -> AnalyticsDashboardData:
    cache_key = _cache_key("dashboard", f"days_{days}")
    cached = _cache_get(AnalyticsDashboardData, cache_key)
    if cached is not None:
        return cached

    rows, errors = _run_dashboard_queries(days)
    if errors:
        payload = _empty_dashboard(days, "error", "; ".join(errors.values()))
        return AnalyticsDashboardData.model_validate(payload)

    summary_row = rows["summary"][0] if rows["summary"] else []
    hourly_rows = rows["hourly"]
    camera_rows = rows["camera"]
    daily_rows = rows["daily"]

    total_detections = _safe_int(summary_row[0] if len(summary_row) > 0 else 0)
    if total_detections == 0:
        payload = _empty_dashboard(days, "empty")
        _cache_set(cache_key, payload, _cache_ttl_for_status(DASHBOARD_CACHE_TTL_SEC, "empty"))
        return AnalyticsDashboardData.model_validate(payload)

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
    status = _cacheable_status(data)
    if status is not None:
        _cache_set(cache_key, data, _cache_ttl_for_status(DASHBOARD_CACHE_TTL_SEC, status))
    return AnalyticsDashboardData.model_validate(data)


HEATMAP_QUERY_TIMEOUT = 15.0


@router.get("/heatmap", response_model=PresenceHeatmapData)
def get_presence_heatmap(
    camera_id: str = Query(...),
    days: int = Query(default=7, ge=1, le=MAX_DAYS),
    metric: str = Query(default="presence"),
) -> PresenceHeatmapData:
    _validate_camera_id(camera_id)
    cache_key = _cache_key("heatmap", camera_id, f"days_{days}", f"metric_{metric}")
    cached = _cache_get(PresenceHeatmapData, cache_key)
    if cached is not None:
        return cached

    now = datetime.now(timezone.utc)
    ttl_sec = HEATMAP_CACHE_TTL_1D_SEC if days <= 1 else HEATMAP_CACHE_TTL_LONG_SEC

    def _empty(status: str, msg: str | None = None) -> PresenceHeatmapData:
        return PresenceHeatmapData.model_validate({
            "generated_at": now.isoformat(),
            "range_label": f"Last {days} days",
            "camera_id": camera_id,
            "data_status": status,
            "error_message": msg,
            "grid_rows": 24,
            "grid_cols": 32,
            "cells": [],
        })

    try:
        rows = trino_query(heatmap_presence_sql(camera_id, days), HEATMAP_QUERY_TIMEOUT)
    except (HTTPError, URLError, TimeoutError, RuntimeError, OSError) as exc:
        return _empty("error", str(exc))

    if not rows:
        payload = {
            "generated_at": now.isoformat(),
            "range_label": f"Last {days} days",
            "camera_id": camera_id,
            "data_status": "empty",
            "error_message": None,
            "grid_rows": 24,
            "grid_cols": 32,
            "cells": [],
        }
        _cache_set(cache_key, payload, _cache_ttl_for_status(ttl_sec, "empty"))
        return PresenceHeatmapData.model_validate(payload)

    raw_counts = [_safe_int(r[2]) for r in rows]
    max_count = max(raw_counts, default=0)
    log_max = math.log1p(max_count)

    cells = []
    for r, cnt in zip(rows, raw_counts):
        if cnt <= 0:
            continue
        normalized = int(math.log1p(cnt) / log_max * 100) if log_max > 0 else 0
        if normalized > 0:
            cells.append({"row": _safe_int(r[0]), "col": _safe_int(r[1]), "value": normalized})

    payload = {
        "generated_at": now.isoformat(),
        "range_label": f"Last {days} days",
        "camera_id": camera_id,
        "data_status": "ready",
        "error_message": None,
        "grid_rows": 24,
        "grid_cols": 32,
        "cells": cells,
    }
    _cache_set(cache_key, payload, _cache_ttl_for_status(ttl_sec, "ready"))
    return PresenceHeatmapData.model_validate(payload)
