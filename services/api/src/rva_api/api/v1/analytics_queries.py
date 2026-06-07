from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.request import Request, urlopen

MAX_DAYS = 31
HEATMAP_ROWS = 6
HEATMAP_COLS = 8


def _trino_url() -> str:
    return os.getenv("TRINO_URL", "http://localhost:8083").rstrip("/")


def _query_timeout() -> float:
    return float(os.getenv("TRINO_QUERY_TIMEOUT_SEC", "5"))


def _max_query_wait() -> float:
    return float(os.getenv("TRINO_QUERY_MAX_WAIT_SEC", "20"))


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


def hourly_sql(days: int) -> str:
    return f"""
        SELECT
          concat(lpad(CAST(hour(capture_ts) AS varchar), 2, '0'), ':00') AS hour_label,
          COUNT(*) AS detections
        FROM lakehouse.rva.silver_detections
        WHERE capture_ts >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
        GROUP BY hour(capture_ts)
        ORDER BY hour(capture_ts)
    """


def camera_sql(days: int) -> str:
    return f"""
        WITH camera_counts AS (
          SELECT camera_id, COUNT(*) AS detections
          FROM lakehouse.rva.silver_detections
          WHERE capture_ts >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
          GROUP BY camera_id
        ),
        total_counts AS (
          SELECT SUM(detections) AS total_detections FROM camera_counts
        )
        SELECT
          camera_id,
          detections,
          ROUND(detections * 100.0 / NULLIF(total_detections, 0), 1) AS share
        FROM camera_counts CROSS JOIN total_counts
        ORDER BY detections DESC
    """


def heatmap_sql(days: int) -> str:
    return f"""
        SELECT
          LEAST({HEATMAP_ROWS - 1}, GREATEST(0, CAST(FLOOR((((bbox_y1 + bbox_y2) / 2.0) / img_h) * {HEATMAP_ROWS}) AS integer))) AS row_index,
          LEAST({HEATMAP_COLS - 1}, GREATEST(0, CAST(FLOOR((((bbox_x1 + bbox_x2) / 2.0) / img_w) * {HEATMAP_COLS}) AS integer))) AS col_index,
          COUNT(*) AS detections
        FROM lakehouse.rva.silver_detections
        WHERE capture_ts >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
          AND img_w > 0
          AND img_h > 0
        GROUP BY 1, 2
        ORDER BY 1, 2
    """


def dwell_sql(days: int) -> str:
    return f"""
        SELECT
          CASE
            WHEN duration_sec < 30 THEN '< 30s'
            WHEN duration_sec < 60 THEN '30s - 1m'
            WHEN duration_sec < 120 THEN '1m - 2m'
            WHEN duration_sec < 300 THEN '2m - 5m'
            WHEN duration_sec < 600 THEN '5m - 10m'
            ELSE '> 10m'
          END AS band,
          COUNT(*) AS tracks
        FROM lakehouse.rva.gold_track_summary
        WHERE visit_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          AND duration_sec >= 0
        GROUP BY 1
    """


def daily_sql(days: int) -> str:
    return f"""
        WITH hourly AS (
          SELECT CAST(capture_ts AS date) AS visit_date, hour(capture_ts) AS visit_hour, COUNT(*) AS detections
          FROM lakehouse.rva.silver_detections
          WHERE capture_ts >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
          GROUP BY 1, 2
        ),
        daily AS (
          SELECT
            visit_date,
            SUM(detections) AS total_detections,
            max_by(visit_hour, detections) AS peak_hour,
            MAX(detections) AS peak_detections
          FROM hourly
          GROUP BY visit_date
        )
        SELECT
          CAST(daily.visit_date AS varchar) AS date_label,
          daily.total_detections,
          concat(lpad(CAST(daily.peak_hour AS varchar), 2, '0'), ':00 (', CAST(daily.peak_detections AS varchar), ')') AS peak,
          0 AS avg_dwell_sec
        FROM daily
        ORDER BY daily.visit_date DESC
        LIMIT 7
    """


def avg_dwell_sql(days: int) -> str:
    return f"""
        SELECT AVG(duration_sec) AS avg_dwell_sec, COUNT(*) AS tracks
        FROM lakehouse.rva.gold_track_summary
        WHERE visit_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          AND duration_sec >= 0
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
