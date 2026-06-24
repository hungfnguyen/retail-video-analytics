#!/usr/bin/env python3
"""Lightweight data-quality + freshness checks for the lakehouse serving layer.

Writes one row per check into lakehouse.rva_gold_serving.gold_serving_data_quality_results
and exits non-zero if any check has status='error', so the Airflow
`gold_quality_checks` DAG fails (and can alert) on real problems.

Severity policy (kept lean on purpose):
- freshness lags  -> 'warn'  : data can legitimately pause in dev; does NOT fail the run.
- negative measures -> 'error': structural corruption; fails the run.
- serving empty while Silver has today's data -> 'warn'.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import uuid

import apply_ddl
import trino_client as trino

GS = "lakehouse.rva_gold_serving"
RVA = "lakehouse.rva"
FRESHNESS_MIN = int(os.getenv("DQ_FRESHNESS_MIN", "60"))
DQ_RECENT_DAYS = int(os.getenv("DQ_RECENT_DAYS", "7"))

# (table, column) additive measures that must never be negative.
NON_NEGATIVE = [
    ("gold_serving_traffic_hourly", "detection_count"),
    ("gold_serving_traffic_hourly", "unique_tracks"),
    ("gold_serving_traffic_hourly", "max_people_count"),
    ("gold_serving_traffic_daily", "unique_tracks"),
    ("gold_serving_queue_hourly", "sessions"),
    ("gold_serving_queue_hourly", "max_wait_sec"),
    ("gold_serving_zone_hourly", "occupied_minutes"),
    ("gold_serving_zone_hourly", "detection_count"),
    ("gold_serving_zone_hourly", "unique_tracks"),
    ("gold_serving_zone_daily", "unique_tracks"),
    ("gold_serving_dwell_daily", "track_count"),
]

# Serving tables that should hold today's partition when Silver has today's data.
TODAY_PRESENCE = [
    "gold_serving_traffic_hourly",
    "gold_serving_heatmap_tile_5min",
    "gold_serving_zone_hourly",
]

# Business keys that should be unique per serving table for recent partitions.
DUPLICATE_KEYS = {
    "gold_serving_traffic_hourly": ["store_id", "camera_id", "bucket_hour", "metric_date"],
    "gold_serving_traffic_daily": ["store_id", "camera_id", "metric_date"],
    "gold_serving_heatmap_tile_5min": ["store_id", "camera_id", "bucket_start", "metric_date", "tile_x", "tile_y"],
    "gold_serving_heatmap_tile_hour": ["store_id", "camera_id", "bucket_hour", "metric_date", "tile_x", "tile_y"],
    "gold_serving_queue_hourly": ["store_id", "camera_id", "queue_zone_id", "bucket_hour", "metric_date"],
    "gold_serving_queue_daily": ["store_id", "camera_id", "queue_zone_id", "metric_date"],
    "gold_serving_zone_hourly": ["store_id", "camera_id", "zone_id", "zone_type", "bucket_hour", "metric_date"],
    "gold_serving_zone_daily": ["store_id", "camera_id", "zone_id", "zone_type", "metric_date"],
    "gold_serving_dwell_daily": ["store_id", "camera_id", "metric_date"],
    "gold_serving_executive_daily": ["store_id", "metric_date"],
    "gold_serving_alert_hourly": ["store_id", "camera_id", "alert_type", "severity", "bucket_hour", "metric_date"],
    "gold_serving_alert_daily": ["store_id", "camera_id", "alert_type", "severity", "metric_date"],
}


def _sql_str(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _write(run_id, check_name, table_name, severity, status, observed, expected):
    partition_date = dt.date.today().isoformat()
    sql = f"""
        INSERT INTO {GS}.gold_serving_data_quality_results
        SELECT 'gold_quality_checks', {_sql_str(run_id)}, {_sql_str(check_name)}, {_sql_str(table_name)},
               DATE '{partition_date}', {_sql_str(severity)}, {_sql_str(status)},
               {_sql_str(str(observed))}, {_sql_str(expected)},
               CAST(current_timestamp AS timestamp(6))
    """
    try:
        trino.run(sql)
    except Exception as exc:  # DQ write is best-effort; never mask the check result
        print(f"  [warn] dq write failed for {check_name}/{table_name}: {exc}", file=sys.stderr)


def check_silver_freshness(run_id) -> bool:
    lag = trino.scalar(
        f"SELECT date_diff('minute', max(capture_ts), current_timestamp) FROM {RVA}.silver_detections_v2"
    )
    stale = lag is None or int(lag) > FRESHNESS_MIN
    status = "warn" if stale else "ok"
    _write(run_id, "silver_freshness", "silver_detections_v2", "warn", status,
           f"lag_min={lag}", f"<= {FRESHNESS_MIN} min")
    print(f"  {status:5} silver_freshness lag_min={lag}")
    return False  # freshness never fails the run


def check_serving_freshness(run_id) -> bool:
    lag = trino.scalar(
        f"SELECT date_diff('minute', max(refreshed_at), current_timestamp) "
        f"FROM {GS}.gold_serving_refresh_audit WHERE status = 'ok'"
    )
    stale = lag is None or int(lag) > FRESHNESS_MIN
    status = "warn" if stale else "ok"
    _write(run_id, "serving_freshness", "gold_serving_refresh_audit", "warn", status,
           f"lag_min={lag}", f"<= {FRESHNESS_MIN} min")
    print(f"  {status:5} serving_freshness lag_min={lag}")
    return False


def check_non_negative(run_id) -> bool:
    any_error = False
    for table, column in NON_NEGATIVE:
        bad = trino.scalar(f"SELECT COUNT(*) FROM {GS}.{table} WHERE {column} < 0") or 0
        status = "error" if int(bad) > 0 else "ok"
        if status == "error":
            any_error = True
        _write(run_id, f"non_negative.{column}", table, "error", status,
               f"violations={bad}", f"{column} >= 0")
        print(f"  {status:5} non_negative {table}.{column} violations={bad}")
    return any_error


def check_today_presence(run_id) -> bool:
    silver_today = trino.scalar(
        f"SELECT COUNT(*) FROM {RVA}.silver_detections_v2 WHERE capture_date = current_date"
    ) or 0
    for table in TODAY_PRESENCE:
        rows = trino.scalar(f"SELECT COUNT(*) FROM {GS}.{table} WHERE metric_date = current_date") or 0
        missing = int(silver_today) > 0 and int(rows) == 0
        status = "warn" if missing else "ok"
        _write(run_id, "today_presence", table, "warn", status,
               f"silver_today={silver_today},serving_today={rows}", "serving_today > 0 when silver_today > 0")
        print(f"  {status:5} today_presence {table} serving_today={rows} (silver_today={silver_today})")
    return False  # presence gap is a warning, not a hard failure


def check_duplicate_keys(run_id) -> bool:
    any_error = False
    recent_start_expr = f"date_add('day', -{DQ_RECENT_DAYS}, current_date)"
    for table, key_columns in DUPLICATE_KEYS.items():
        key_sql = ", ".join(key_columns)
        bad = trino.scalar(
            f"""
            SELECT COUNT(*) FROM (
                SELECT {key_sql}
                FROM {GS}.{table}
                WHERE metric_date >= {recent_start_expr}
                GROUP BY {key_sql}
                HAVING COUNT(*) > 1
            )
            """
        ) or 0
        status = "error" if int(bad) > 0 else "ok"
        if status == "error":
            any_error = True
        _write(
            run_id,
            "duplicate_keys",
            table,
            "error",
            status,
            f"duplicate_groups={bad}",
            f"unique over ({key_sql}) for metric_date >= current_date - {DQ_RECENT_DAYS}d",
        )
        print(f"  {status:5} duplicate_keys {table} duplicate_groups={bad}")
    return any_error


CHECKS = [
    check_silver_freshness,
    check_serving_freshness,
    check_non_negative,
    check_today_presence,
    check_duplicate_keys,
]


def main() -> None:
    apply_ddl.ensure_schema()
    run_id = uuid.uuid4().hex[:12]
    print(
        f"quality_checks run_id={run_id} freshness_threshold={FRESHNESS_MIN}min "
        f"duplicate_window_days={DQ_RECENT_DAYS}"
    )
    errors = 0
    for check in CHECKS:
        try:
            if check(run_id):
                errors += 1
        except Exception as exc:
            errors += 1
            print(f"  ERROR check {check.__name__} crashed: {exc}", file=sys.stderr)
    print(f"done: {errors} error-level check(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
