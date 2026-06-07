from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.request import Request, urlopen

MAX_DAYS = 31


def _trino_url() -> str:
    return os.getenv("TRINO_URL", "http://localhost:8083").rstrip("/")


def _query_timeout() -> float:
    return float(os.getenv("TRINO_QUERY_TIMEOUT_SEC", "5"))


def _max_query_wait() -> float:
    return float(os.getenv("TRINO_QUERY_MAX_WAIT_SEC", "60"))


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "text/plain",
        "X-Trino-User": os.getenv("TRINO_USER", "rva_api"),
        "X-Trino-Catalog": os.getenv("TRINO_CATALOG", "lakehouse"),
        "X-Trino-Schema": os.getenv("TRINO_SCHEMA", "rva"),
    }


def _read_json_response(url: str, request: Request | None = None) -> dict[str, Any]:
    with urlopen(request or url, timeout=_query_timeout()) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def _cancel_query(next_uri: str | None) -> None:
    if not next_uri:
        return
    try:
        request = Request(next_uri, method="DELETE")
        urlopen(request, timeout=1).close()
    except Exception:
        return


def trino_query(sql: str, max_wait: float | None = None) -> list[list[Any]]:
    started_at = time.monotonic()
    query_max_wait = _max_query_wait() if max_wait is None else max_wait
    request = Request(
        f"{_trino_url()}/v1/statement",
        data=sql.encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    payload = _read_json_response("", request)
    rows: list[list[Any]] = []

    while True:
        if payload.get("error"):
            message = payload["error"].get("message", "Trino query failed.")
            raise RuntimeError(message)

        stats = payload.get("stats") or {}
        elapsed = time.monotonic() - started_at
        if elapsed > query_max_wait:
            state = stats.get("state", "unknown")
            _cancel_query(payload.get("nextUri"))
            raise RuntimeError(f"Trino query did not finish within {query_max_wait:.0f}s. Current state: {state}.")

        rows.extend(payload.get("data") or [])
        next_uri = payload.get("nextUri")
        if not next_uri:
            return rows
        payload = _read_json_response(next_uri)


def summary_sql(days: int) -> str:
    return f"""
        WITH daily AS (
          SELECT *
          FROM lakehouse.rva.gold_camera_daily_metrics
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
        ),
        dwell AS (
          SELECT *
          FROM lakehouse.rva.gold_camera_daily_dwell
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
        )
        SELECT
          COALESCE(SUM(daily.detections), 0) AS total_detections,
          COALESCE(SUM(daily.unique_tracks), 0) AS unique_tracks,
          COUNT(DISTINCT daily.metric_date) AS active_days,
          COALESCE(SUM(daily.avg_conf * daily.detections) / NULLIF(SUM(daily.detections), 0), 0) AS avg_conf,
          COALESCE(SUM(daily.detections) / NULLIF(COUNT(DISTINCT daily.metric_date), 0), 0) AS avg_detections_per_active_day,
          COALESCE(SUM(dwell.total_dwell_sec) / NULLIF(SUM(dwell.track_count), 0), 0) AS avg_dwell_sec,
          COALESCE(SUM(dwell.track_count), 0) AS track_count,
          COALESCE(SUM(dwell.long_dwell_tracks), 0) AS long_dwell_tracks,
          COALESCE(SUM(dwell.short_dwell_tracks), 0) AS short_dwell_tracks
        FROM daily
        LEFT JOIN dwell
          ON daily.store_id = dwell.store_id
         AND daily.camera_id = dwell.camera_id
         AND daily.metric_date = dwell.metric_date
    """


def hourly_sql(days: int) -> str:
    return f"""
        SELECT
          concat(lpad(CAST(hour_of_day AS varchar), 2, '0'), ':00') AS hour_label,
          SUM(detections) AS detections,
          SUM(unique_tracks) AS unique_tracks,
          ROUND(SUM(detections) / NULLIF(COUNT(DISTINCT metric_date), 0)) AS average
        FROM lakehouse.rva.gold_camera_hourly_metrics
        WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
        GROUP BY hour_of_day
        ORDER BY hour_of_day
    """


def camera_sql(days: int) -> str:
    return f"""
        WITH camera_counts AS (
          SELECT
            camera_id,
            SUM(detections) AS detections,
            SUM(unique_tracks) AS unique_tracks,
            COALESCE(SUM(avg_conf * detections) / NULLIF(SUM(detections), 0), 0) AS avg_conf
          FROM lakehouse.rva.gold_camera_daily_metrics
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          GROUP BY camera_id
        ),
        total_counts AS (
          SELECT SUM(detections) AS total_detections FROM camera_counts
        )
        SELECT
          camera_id,
          detections,
          ROUND(detections * 100.0 / NULLIF(total_detections, 0), 1) AS share,
          unique_tracks,
          avg_conf
        FROM camera_counts CROSS JOIN total_counts
        ORDER BY detections DESC
    """


def daily_sql(days: int) -> str:
    return f"""
        WITH daily AS (
          SELECT
            metric_date,
            SUM(detections) AS total_detections,
            SUM(unique_tracks) AS unique_tracks,
            COALESCE(SUM(avg_conf * detections) / NULLIF(SUM(detections), 0), 0) AS avg_conf
          FROM lakehouse.rva.gold_camera_daily_metrics
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          GROUP BY 1
        ),
        hourly AS (
          SELECT metric_date, hour_of_day, SUM(detections) AS detections
          FROM lakehouse.rva.gold_camera_hourly_metrics
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          GROUP BY 1, 2
        ),
        hourly_ranked AS (
          SELECT
            metric_date,
            hour_of_day,
            detections,
            ROW_NUMBER() OVER (PARTITION BY metric_date ORDER BY detections DESC, hour_of_day) AS rn
          FROM hourly
        ),
        dwell AS (
          SELECT
            metric_date,
            SUM(track_count) AS track_count,
            COALESCE(SUM(total_dwell_sec) / NULLIF(SUM(track_count), 0), 0) AS avg_dwell_sec
          FROM lakehouse.rva.gold_camera_daily_dwell
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          GROUP BY 1
        )
        SELECT
          CAST(daily.metric_date AS varchar) AS date_label,
          daily.total_detections,
          daily.unique_tracks,
          concat(lpad(CAST(hourly_ranked.hour_of_day AS varchar), 2, '0'), ':00 (', CAST(hourly_ranked.detections AS varchar), ')') AS peak,
          COALESCE(dwell.avg_dwell_sec, 0) AS avg_dwell_sec,
          daily.avg_conf
        FROM daily
        LEFT JOIN hourly_ranked
          ON daily.metric_date = hourly_ranked.metric_date
         AND hourly_ranked.rn = 1
        LEFT JOIN dwell
          ON daily.metric_date = dwell.metric_date
        ORDER BY daily.metric_date DESC
        LIMIT 7
    """


def queue_zone_summary_sql(days: int) -> str:
    return f"""
        SELECT
          queue_zone_id,
          COUNT(*) AS total_sessions,
          ROUND(AVG(CAST(wait_time_sec AS double)), 1) AS avg_wait_sec,
          MAX(wait_time_sec) AS max_wait_sec,
          COUNT(DISTINCT global_track_id) AS unique_visitors
        FROM lakehouse.rva.gold_queue_sessions
        WHERE visit_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          AND wait_time_sec >= 0
        GROUP BY queue_zone_id
        ORDER BY avg_wait_sec DESC
    """


def alerts_history_sql(days: int) -> str:
    return f"""
        SELECT
          alert_id,
          camera_id,
          store_id,
          alert_type,
          severity,
          title,
          description,
          zone,
          CAST(event_ts AS varchar) AS event_ts,
          clip_s3_key
        FROM lakehouse.rva.gold_alerts
        WHERE event_ts >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
        ORDER BY event_ts DESC
        LIMIT 100
    """


def queue_wait_trend_sql(days: int) -> str:
    return f"""
        SELECT
          concat(lpad(CAST(hour(enter_ts) AS varchar), 2, '0'), ':00') AS hour_label,
          ROUND(AVG(CAST(wait_time_sec AS double)), 1) AS avg_wait_sec,
          COUNT(*) AS sessions
        FROM lakehouse.rva.gold_queue_sessions
        WHERE visit_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          AND wait_time_sec >= 0
        GROUP BY hour(enter_ts)
        ORDER BY hour(enter_ts)
    """
