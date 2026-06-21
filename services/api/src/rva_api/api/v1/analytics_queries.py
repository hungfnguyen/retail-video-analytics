from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.request import Request, urlopen

MAX_DAYS = 31


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _camera_filter(camera_id: str | None, column: str = "camera_id") -> str:
    if not camera_id:
        return ""
    return f" AND {column} = {_sql_string(camera_id)}"


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


def summary_sql(days: int, camera_id: str | None = None) -> str:
    return f"""
        WITH traffic AS (
          SELECT
            COALESCE(SUM(detection_count), 0) AS total_detections,
            COUNT(DISTINCT metric_date) AS active_days,
            COALESCE(SUM(avg_conf * detection_count) / NULLIF(SUM(detection_count), 0), 0) AS avg_conf
          FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
            {_camera_filter(camera_id)}
        ),
        dwell AS (
          SELECT
            COALESCE(SUM(track_count), 0) AS track_count,
            COALESCE(SUM(avg_dwell_sec * track_count) / NULLIF(SUM(track_count), 0), 0) AS avg_dwell_sec,
            COALESCE(SUM(long_dwell_tracks), 0) AS long_dwell_tracks,
            COALESCE(SUM(short_dwell_tracks), 0) AS short_dwell_tracks,
            COALESCE(SUM(medium_dwell_tracks), 0) AS medium_dwell_tracks
          FROM lakehouse.rva_gold_serving.gold_serving_dwell_daily
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
            {_camera_filter(camera_id)}
        )
        SELECT
          traffic.total_detections,
          traffic.active_days,
          traffic.avg_conf,
          COALESCE(traffic.total_detections / NULLIF(traffic.active_days, 0), 0) AS avg_detections_per_active_day,
          dwell.avg_dwell_sec,
          dwell.long_dwell_tracks,
          dwell.short_dwell_tracks,
          dwell.medium_dwell_tracks
        FROM traffic
        CROSS JOIN dwell
    """


def hourly_sql(days: int, camera_id: str | None = None) -> str:
    return f"""
        WITH hourly_rollup AS (
          SELECT
            hour_of_day,
            SUM(detection_count) AS detections,
            ROUND(SUM(detection_count) / NULLIF(COUNT(DISTINCT metric_date), 0)) AS average
          FROM lakehouse.rva_gold_serving.gold_serving_traffic_hourly
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
            {_camera_filter(camera_id)}
          GROUP BY hour_of_day
        )
        SELECT
          concat(lpad(CAST(hour_of_day AS varchar), 2, '0'), ':00') AS hour_label,
          detections,
          average
        FROM hourly_rollup
        ORDER BY hour_of_day
    """


def camera_sql(days: int) -> str:
    return f"""
        WITH camera_counts AS (
          SELECT
            camera_id,
            SUM(detection_count) AS detections,
            COALESCE(SUM(avg_conf * detection_count) / NULLIF(SUM(detection_count), 0), 0) AS avg_conf
          FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          GROUP BY camera_id
        ),
        total_counts AS (
          SELECT SUM(detections) AS total_detections FROM camera_counts
        )
        SELECT
          camera_counts.camera_id,
          camera_counts.detections,
          ROUND(camera_counts.detections * 100.0 / NULLIF(total_counts.total_detections, 0), 1) AS share,
          camera_counts.avg_conf
        FROM camera_counts
        CROSS JOIN total_counts
        ORDER BY camera_counts.detections DESC
    """


def daily_sql(days: int, camera_id: str | None = None) -> str:
    if camera_id:
        return f"""
            WITH traffic AS (
              SELECT
                store_id,
                camera_id,
                metric_date,
                SUM(detection_count) AS total_detections,
                COALESCE(SUM(avg_conf * detection_count) / NULLIF(SUM(detection_count), 0), 0) AS avg_confidence,
                MAX_BY(peak_hour, peak_hour_detections) AS peak_hour
              FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily
              WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
                {_camera_filter(camera_id)}
              GROUP BY store_id, camera_id, metric_date
            ),
            dwell AS (
              SELECT
                store_id,
                camera_id,
                metric_date,
                ROUND(SUM(avg_dwell_sec * track_count) / NULLIF(SUM(track_count), 0), 1) AS avg_dwell_sec
              FROM lakehouse.rva_gold_serving.gold_serving_dwell_daily
              WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
                {_camera_filter(camera_id)}
              GROUP BY store_id, camera_id, metric_date
            ),
            queue AS (
              SELECT
                store_id,
                camera_id,
                metric_date,
                ROUND(SUM(avg_wait_sec * sessions) / NULLIF(SUM(sessions), 0), 1) AS avg_queue_wait_sec
              FROM lakehouse.rva_gold_serving.gold_serving_queue_daily
              WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
                {_camera_filter(camera_id)}
              GROUP BY store_id, camera_id, metric_date
            ),
            alerts AS (
              SELECT
                store_id,
                camera_id,
                metric_date,
                SUM(alert_count) AS total_alerts
              FROM lakehouse.rva_gold_serving.gold_serving_alert_daily
              WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
                {_camera_filter(camera_id)}
              GROUP BY store_id, camera_id, metric_date
            )
            SELECT
              CAST(traffic.metric_date AS varchar) AS date_label,
              traffic.total_detections,
              concat(lpad(CAST(traffic.peak_hour AS varchar), 2, '0'), ':00') AS peak,
              COALESCE(dwell.avg_dwell_sec, 0) AS avg_dwell_sec,
              traffic.avg_confidence,
              COALESCE(queue.avg_queue_wait_sec, 0) AS avg_queue_wait_sec,
              COALESCE(alerts.total_alerts, 0) AS total_alerts
            FROM traffic
            LEFT JOIN dwell
              ON traffic.store_id = dwell.store_id
             AND traffic.camera_id = dwell.camera_id
             AND traffic.metric_date = dwell.metric_date
            LEFT JOIN queue
              ON traffic.store_id = queue.store_id
             AND traffic.camera_id = queue.camera_id
             AND traffic.metric_date = queue.metric_date
            LEFT JOIN alerts
              ON traffic.store_id = alerts.store_id
             AND traffic.camera_id = alerts.camera_id
             AND traffic.metric_date = alerts.metric_date
            ORDER BY traffic.metric_date ASC
        """
    return f"""
        SELECT
          CAST(metric_date AS varchar) AS date_label,
          total_detections,
          concat(lpad(CAST(peak_hour AS varchar), 2, '0'), ':00') AS peak,
          COALESCE(avg_dwell_sec, 0) AS avg_dwell_sec,
          COALESCE(avg_queue_wait_sec, 0) AS avg_queue_wait_sec,
          COALESCE(total_alerts, 0) AS total_alerts
        FROM lakehouse.rva_gold_serving.gold_serving_executive_daily
        WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
        ORDER BY metric_date ASC
    """


def visitors_series_sql(days: int, camera_id: str | None = None) -> str:
    if days <= 1:
        return f"""
            SELECT
              hour_label,
              detections
            FROM (
              SELECT
                concat(lpad(CAST(hour_of_day AS varchar), 2, '0'), ':00') AS hour_label,
                SUM(detection_count) AS detections
              FROM lakehouse.rva_gold_serving.gold_serving_traffic_hourly
              WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
                {_camera_filter(camera_id)}
              GROUP BY hour_of_day
            )
            ORDER BY hour_label
        """
    return f"""
        SELECT
          CAST(metric_date AS varchar) AS date_label,
          SUM(detection_count) AS detections
        FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily
        WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          {_camera_filter(camera_id)}
        GROUP BY metric_date
        ORDER BY metric_date
    """


def weekday_pattern_sql(days: int, camera_id: str | None = None) -> str:
    return f"""
        WITH daily AS (
          SELECT metric_date, SUM(detection_count) AS visitors
          FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
            {_camera_filter(camera_id)}
          GROUP BY metric_date
        )
        SELECT
          CASE day_of_week(metric_date)
            WHEN 1 THEN 'Mon'
            WHEN 2 THEN 'Tue'
            WHEN 3 THEN 'Wed'
            WHEN 4 THEN 'Thu'
            WHEN 5 THEN 'Fri'
            WHEN 6 THEN 'Sat'
            WHEN 7 THEN 'Sun'
          END AS weekday,
          day_of_week(metric_date) AS weekday_order,
          CAST(ROUND(AVG(visitors)) AS BIGINT) AS avg_visitors
        FROM daily
        GROUP BY 1, 2
        ORDER BY weekday_order
    """


def peak_heatmap_sql(days: int, camera_id: str | None = None) -> str:
    return f"""
        SELECT
          CASE day_of_week(metric_date)
            WHEN 1 THEN 'Mon'
            WHEN 2 THEN 'Tue'
            WHEN 3 THEN 'Wed'
            WHEN 4 THEN 'Thu'
            WHEN 5 THEN 'Fri'
            WHEN 6 THEN 'Sat'
            WHEN 7 THEN 'Sun'
          END AS weekday,
          day_of_week(metric_date) AS weekday_order,
          hour_of_day,
          SUM(detection_count) AS visitors
        FROM lakehouse.rva_gold_serving.gold_serving_traffic_hourly
        WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          {_camera_filter(camera_id)}
        GROUP BY 1, 2, 3
        ORDER BY weekday_order, hour_of_day
    """


def top_zones_sql(days: int, camera_id: str | None = None) -> str:
    return f"""
        WITH zones AS (
          SELECT
            zone_id,
            REGEXP_REPLACE(zone_id, '_', ' ') AS zone_name,
            SUM(detection_count) AS visitors,
            AVG(avg_occupancy) AS avg_occupancy,
            SUM(occupied_minutes) AS occupied_minutes
          FROM lakehouse.rva_gold_serving.gold_serving_zone_daily
          WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
            {_camera_filter(camera_id)}
          GROUP BY zone_id
        ),
        totals AS (
          SELECT SUM(visitors) AS total_visitors
          FROM zones
        )
        SELECT
          zones.zone_id,
          zones.zone_name,
          zones.visitors,
          ROUND(zones.visitors * 100.0 / NULLIF(totals.total_visitors, 0), 1) AS share,
          ROUND(zones.avg_occupancy, 1) AS avg_occupancy,
          CAST(zones.occupied_minutes AS BIGINT) AS occupied_minutes
        FROM zones
        CROSS JOIN totals
        ORDER BY zones.visitors DESC
        LIMIT 5
    """


def dwell_trend_sql(days: int, camera_id: str | None = None) -> str:
    return f"""
        SELECT
          CAST(metric_date AS varchar) AS date_label,
          ROUND(SUM(avg_dwell_sec * track_count) / NULLIF(SUM(track_count), 0), 1) AS avg_dwell_sec,
          ROUND(SUM(p50_dwell_sec * track_count) / NULLIF(SUM(track_count), 0), 1) AS p50_dwell_sec,
          ROUND(SUM(p90_dwell_sec * track_count) / NULLIF(SUM(track_count), 0), 1) AS p90_dwell_sec
        FROM lakehouse.rva_gold_serving.gold_serving_dwell_daily
        WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          {_camera_filter(camera_id)}
        GROUP BY metric_date
        ORDER BY metric_date
    """


def queue_zone_summary_sql(days: int, camera_id: str | None = None) -> str:
    return f"""
        SELECT
          queue_zone_id,
          SUM(sessions) AS total_sessions,
          ROUND(SUM(avg_wait_sec * sessions) / NULLIF(SUM(sessions), 0), 1) AS avg_wait_sec,
          MAX(max_wait_sec) AS max_wait_sec
        FROM lakehouse.rva_gold_serving.gold_serving_queue_daily
        WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          {_camera_filter(camera_id)}
        GROUP BY queue_zone_id
        ORDER BY avg_wait_sec DESC
    """


def alerts_history_sql(days: int, camera_id: str | None = None) -> str:
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
          {_camera_filter(camera_id)}
        ORDER BY event_ts DESC
        LIMIT 100
    """


def heatmap_presence_sql(camera_id: str, days: int) -> str:
    source_table = "lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min" if days <= 1 else "lakehouse.rva_gold_serving.gold_serving_heatmap_tile_hour"
    bucket_column = "bucket_start" if days <= 1 else "bucket_hour"
    return f"""
        SELECT
            tile_y AS grid_row,
            tile_x AS grid_col,
            SUM(detection_count) AS presence_count
        FROM {source_table}
        WHERE camera_id = '{camera_id}'
          AND {bucket_column} >= CURRENT_TIMESTAMP - INTERVAL '{days}' DAY
        GROUP BY 1, 2
        ORDER BY 1, 2
    """


def queue_wait_trend_sql(days: int, camera_id: str | None = None) -> str:
    return f"""
        SELECT
          concat(lpad(CAST(hour(bucket_hour) AS varchar), 2, '0'), ':00') AS hour_label,
          ROUND(SUM(avg_wait_sec * sessions) / NULLIF(SUM(sessions), 0), 1) AS avg_wait_sec,
          SUM(sessions) AS sessions
        FROM lakehouse.rva_gold_serving.gold_serving_queue_hourly
        WHERE metric_date >= CURRENT_DATE - INTERVAL '{days}' DAY
          {_camera_filter(camera_id)}
        GROUP BY hour(bucket_hour)
        ORDER BY hour(bucket_hour)
    """
