#!/usr/bin/env python3
"""Lightweight Iceberg maintenance runner for Gold serving tables.

Runs OPTIMIZE on hot serving/source tables and writes simple data-quality
results into lakehouse.rva_gold_serving.gold_serving_data_quality_results.

This script is intentionally engine-agnostic orchestration glue: Airflow calls
it as a bounded maintenance task without embedding Trino/Iceberg logic in the
DAG itself.
"""

from __future__ import annotations

import datetime as dt
import uuid

import apply_ddl
import trino_client as trino

# Upsert Gold fact tables: streaming commits every 30s → data + position-delete
# files pile up. Optimize merges deletes into data files so batch/Trino readers
# don't stall in BaseDeleteLoader.loadPositionDeletes over remote S3.
# Append-only silver is included only for small-file consolidation (no delete files).
OPTIMIZE_TABLES = [
    "lakehouse.rva.silver_detections_v2",
    "lakehouse.rva.gold_queue_sessions_v2",
    "lakehouse.rva.gold_track_summary_v2",
    "lakehouse.rva.gold_alerts",
    "lakehouse.rva.gold_alert_events",
    "lakehouse.rva.gold_camera_hourly_metrics",
    "lakehouse.rva.gold_camera_daily_metrics",
    "lakehouse.rva.gold_camera_daily_dwell",
    "lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min",
    "lakehouse.rva_gold_serving.gold_serving_heatmap_tile_hour",
    "lakehouse.rva_gold_serving.gold_serving_traffic_hourly",
    "lakehouse.rva_gold_serving.gold_serving_traffic_daily",
    "lakehouse.rva_gold_serving.gold_serving_queue_hourly",
    "lakehouse.rva_gold_serving.gold_serving_queue_daily",
    "lakehouse.rva_gold_serving.gold_serving_zone_hourly",
    "lakehouse.rva_gold_serving.gold_serving_zone_daily",
    "lakehouse.rva_gold_serving.gold_serving_dwell_daily",
    "lakehouse.rva_gold_serving.gold_serving_executive_daily",
]

# Tables where old snapshots should be expired to free S3 storage.
# Upsert fact tables accumulate ~2880 snapshots/day (one per 30s checkpoint).
# After optimize, the old data+delete files are unreferenced → expiry frees them.
# silver_detections_v2 is append-only (all data files still live in current
# snapshot) so expiry saves only manifest overhead — skip it here.
EXPIRE_TABLES = [
    "lakehouse.rva.gold_queue_sessions_v2",
    "lakehouse.rva.gold_track_summary_v2",
    "lakehouse.rva.gold_alerts",
    "lakehouse.rva.gold_alert_events",
    "lakehouse.rva.gold_camera_hourly_metrics",
    "lakehouse.rva.gold_camera_daily_metrics",
    "lakehouse.rva.gold_camera_daily_dwell",
    "lakehouse.rva_gold_serving.gold_serving_traffic_hourly",
    "lakehouse.rva_gold_serving.gold_serving_traffic_daily",
    "lakehouse.rva_gold_serving.gold_serving_queue_hourly",
    "lakehouse.rva_gold_serving.gold_serving_queue_daily",
    "lakehouse.rva_gold_serving.gold_serving_zone_hourly",
    "lakehouse.rva_gold_serving.gold_serving_zone_daily",
    "lakehouse.rva_gold_serving.gold_serving_dwell_daily",
    "lakehouse.rva_gold_serving.gold_serving_executive_daily",
]

SNAPSHOT_RETENTION = "7d"

CHECKS = [
    ("gold_serving_heatmap_tile_hour", "rows_non_negative", "SELECT COUNT(*) FROM lakehouse.rva_gold_serving.gold_serving_heatmap_tile_hour"),
    ("gold_serving_traffic_daily", "rows_non_negative", "SELECT COUNT(*) FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily"),
    ("gold_serving_queue_daily", "rows_non_negative", "SELECT COUNT(*) FROM lakehouse.rva_gold_serving.gold_serving_queue_daily"),
    ("gold_serving_zone_daily", "rows_non_negative", "SELECT COUNT(*) FROM lakehouse.rva_gold_serving.gold_serving_zone_daily"),
]


def _sql_str(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _file_stats(table_name: str) -> tuple[int, int]:
    catalog, schema, table = table_name.split(".", 2)
    sql = (
        "SELECT COALESCE(COUNT(*), 0), "
        "COALESCE(CAST(AVG(file_size_in_bytes) AS BIGINT), 0) "
        f'FROM {catalog}.{schema}."{table}$files"'
    )
    result = trino.run(sql)
    if result.rows:
        return int(result.rows[0][0] or 0), int(result.rows[0][1] or 0)
    return 0, 0


def _write_dq_result(run_id: str, check_name: str, table_name: str, observed: str, expected: str, status: str) -> None:
    partition_date = dt.date.today().isoformat()
    sql = f"""
        INSERT INTO lakehouse.rva_gold_serving.gold_serving_data_quality_results
        SELECT 'gold_serving_maintenance', {_sql_str(run_id)}, {_sql_str(check_name)}, {_sql_str(table_name)},
               DATE '{partition_date}', 'info', {_sql_str(status)},
               {_sql_str(observed)}, {_sql_str(expected)},
               CAST(current_timestamp AS timestamp(6))
    """
    trino.run(sql)


def _optimize_table(table_name: str) -> None:
    print(f"optimize {table_name}")
    trino.run(f"ALTER TABLE {table_name} EXECUTE optimize(file_size_threshold => '128MB')", max_wait=900.0)


def _expire_snapshots(table_name: str) -> None:
    print(f"expire_snapshots {table_name}")
    trino.run(
        f"ALTER TABLE {table_name} EXECUTE expire_snapshots(retention_threshold => '{SNAPSHOT_RETENTION}')",
        max_wait=600.0,
    )


def _record_file_stats(run_id: str, table_name: str, before: tuple[int, int], after: tuple[int, int]) -> None:
    observed = f"before_files={before[0]},before_avg={before[1]},after_files={after[0]},after_avg={after[1]}"
    _write_dq_result(run_id, "optimize_file_stats", table_name, observed, "after_files<=before_files", "ok")


def _run_checks(run_id: str) -> None:
    for table_name, check_name, sql in CHECKS:
        rows = trino.scalar(sql)
        observed = str(rows or 0)
        _write_dq_result(run_id, check_name, table_name, observed, ">= 0", "ok")


def main() -> None:
    apply_ddl.ensure_schema()
    run_id = uuid.uuid4().hex[:12]
    print(f"maintenance run_id={run_id}")
    for table_name in OPTIMIZE_TABLES:
        before = _file_stats(table_name)
        try:
            _optimize_table(table_name)
            after = _file_stats(table_name)
            _record_file_stats(run_id, table_name, before, after)
        except Exception as exc:
            print(f"warn optimize failed {table_name}: {exc}")
            _write_dq_result(
                run_id,
                "optimize_failed",
                table_name,
                str(exc),
                "optimize succeeds or is retried later",
                "error",
            )

    for table_name in EXPIRE_TABLES:
        try:
            _expire_snapshots(table_name)
        except Exception as exc:
            print(f"warn expire_snapshots failed {table_name}: {exc}")
            _write_dq_result(
                run_id,
                "expire_snapshots_failed",
                table_name,
                str(exc),
                "expire_snapshots succeeds or is retried later",
                "error",
            )

    _run_checks(run_id)
    print("maintenance done")


if __name__ == "__main__":
    main()
