#!/usr/bin/env python3
"""Legacy Trino fallback for Gold serving refresh.

The scheduled/source-of-truth refresh path is now:

Airflow -> services/flink-jobs/python/submit_batch_job.py -> Flink REST -> GoldServingBatchJob

This script remains in the repo only as a manual/debug fallback and as a reference for
the old Trino-based serving implementation.

Usage:
    python3 refresh_runner.py intraday --allow-legacy
    python3 refresh_runner.py daily --allow-legacy
    python3 refresh_runner.py backfill --start 2026-06-01 --end 2026-06-12 --allow-legacy

It still targets the physical `lakehouse.rva_gold_serving.*` tables already in the repo.

Each serving table: read its refresh .sql, inject the {start}/{end} window,
run the DELETE+INSERT, then write a gold_serving_refresh_audit row (output count,
status, timing). One table failing is logged and does not stop the others;
the process exits non-zero if any refresh failed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import uuid

import apply_ddl
import trino_client as trino

SQL_DIR = os.path.join(os.path.dirname(__file__), "sql", "refresh")

SERVING_TABLES = [
    ("gold_serving_heatmap_tile_5min", "heatmap_5min.sql", "silver_detections_v2"),
    ("gold_serving_heatmap_tile_hour", "heatmap_hour.sql", "gold_serving_heatmap_tile_5min"),
    ("gold_serving_traffic_hourly", "traffic_hourly.sql", "silver_detections_v2"),
    ("gold_serving_traffic_daily", "traffic_daily.sql", "gold_serving_traffic_hourly"),
    ("gold_serving_queue_hourly", "queue_hourly.sql", "gold_queue_sessions_v2"),
    ("gold_serving_queue_daily", "queue_daily.sql", "gold_queue_sessions_v2"),
    ("gold_serving_zone_hourly", "zone_hourly.sql", "silver_detections_v2"),
    ("gold_serving_zone_daily", "zone_daily.sql", "silver_detections_v2"),
    ("gold_serving_dwell_daily", "dwell_daily.sql", "gold_camera_daily_dwell"),
    ("gold_serving_alert_hourly", "alert_hourly.sql", "gold_alerts"),
    ("gold_serving_alert_daily", "alert_daily.sql", "gold_serving_alert_hourly"),
    ("gold_serving_executive_daily", "executive_daily.sql", "gold_serving_traffic_daily"),
]

UTC = dt.UTC


def _sql_str(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _write_audit(run_id, mode, table_name, src, start, end, out_count, status, error, started, finished):
    sql = f"""
        INSERT INTO lakehouse.rva_gold_serving.gold_serving_refresh_audit
        SELECT 'gold_serving_refresh', {_sql_str(run_id)}, {_sql_str(mode)}, {_sql_str(table_name)},
               DATE '{end}', CAST(NULL AS timestamp(6)), CAST(NULL AS timestamp(6)),
               {_sql_str(src)}, CAST(NULL AS bigint), {('CAST(NULL AS bigint)' if out_count is None else str(out_count))},
               {_sql_str(status)}, {_sql_str(error)},
               CAST(TIMESTAMP '{started}' AS timestamp(6)), CAST(TIMESTAMP '{finished}' AS timestamp(6)),
               CAST(current_timestamp AS timestamp(6))
    """
    try:
        trino.run(sql)
    except Exception as exc:  # audit is best-effort
        print(f"  [warn] audit write failed for {table_name}: {exc}", file=sys.stderr)


def refresh_one(run_id, mode, table_name, sql_file, src, start, end):
    path = os.path.join(SQL_DIR, sql_file)
    sql = open(path).read().replace("{start}", start).replace("{end}", end)
    started = dt.datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
    try:
        trino.run_script(sql)
        out = trino.scalar(
            f"SELECT COUNT(*) FROM lakehouse.rva_gold_serving.{table_name} "
            f"WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}'"
        )
        finished = dt.datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
        print(f"  ok   {table_name:36} rows={out}")
        _write_audit(run_id, mode, table_name, src, start, end, out, "ok", None, started, finished)
        return True
    except Exception as exc:
        finished = dt.datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
        print(f"  FAIL {table_name:36} {exc}", file=sys.stderr)
        _write_audit(run_id, mode, table_name, src, start, end, None, "error", str(exc), started, finished)
        return False


def resolve_window(args) -> tuple[str, str]:
    today = dt.date.today()
    if args.mode == "intraday":
        return today.isoformat(), today.isoformat()
    if args.mode == "daily":
        y = (today - dt.timedelta(days=1)).isoformat()
        return y, y
    if args.mode == "backfill":
        if not args.start or not args.end:
            sys.exit("backfill requires --start and --end (YYYY-MM-DD)")
        return args.start, args.end
    sys.exit(f"unknown mode {args.mode}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["intraday", "daily", "backfill"])
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--only", help="comma-separated Gold serving table names to refresh")
    ap.add_argument(
        "--skip-ddl",
        action="store_true",
        help="skip the idempotent DDL bootstrap (e.g. when Airflow runs apply_ddl as a separate task)",
    )
    ap.add_argument(
        "--allow-legacy",
        action="store_true",
        help="acknowledge that this path is a legacy Trino fallback and not the scheduled source of truth",
    )
    args = ap.parse_args()

    if not args.allow_legacy and os.getenv("RVA_ALLOW_LEGACY_TRINO_REFRESH") != "1":
        sys.exit(
            "refresh_runner.py is a legacy Trino fallback. "
            "Use --allow-legacy or set RVA_ALLOW_LEGACY_TRINO_REFRESH=1 for an intentional manual run."
        )

    start, end = resolve_window(args)
    run_id = uuid.uuid4().hex[:12]
    only = set(args.only.split(",")) if args.only else None
    print("warning: refresh_runner.py is a legacy Trino fallback; scheduled refresh uses Flink batch", file=sys.stderr)
    print(f"refresh mode={args.mode} window=[{start}..{end}] run_id={run_id}")

    # Self-heal: ensure the rva_gold_serving schema exists before any INSERT.
    # The schema is dropped on a stack/catalog restart and is not recreated by
    # any Flink job, so refreshing without this would fail with SCHEMA_NOT_FOUND.
    if not args.skip_ddl:
        try:
            count = apply_ddl.ensure_schema()
            print(f"  ddl  rva_gold_serving ensured ({count} tables)")
        except Exception as exc:
            sys.exit(f"DDL bootstrap failed, aborting refresh: {exc}")

    failed = 0
    for table_name, sql_file, src in SERVING_TABLES:
        if only and table_name not in only:
            continue
        if not refresh_one(run_id, args.mode, table_name, sql_file, src, start, end):
            failed += 1
    print(f"done: {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
