#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import requests


DOMAIN_SPECS = {
    "traffic_hourly": {
        "target": "lakehouse.rva_gold_serving.gold_serving_traffic_hourly",
        "source": "lakehouse.rva.silver_detections_v2",
        "source_date_sql": "CAST(capture_ts AS DATE)",
    },
    "traffic_daily": {
        "target": "lakehouse.rva_gold_serving.gold_serving_traffic_daily",
        "source": "lakehouse.rva_gold_serving.gold_serving_traffic_hourly",
        "source_date_sql": "metric_date",
    },
    "heatmap_5min": {
        "target": "lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min",
        "source": "lakehouse.rva.silver_detections_v2",
        "source_date_sql": "CAST(capture_ts AS DATE)",
    },
    "heatmap_hour": {
        "target": "lakehouse.rva_gold_serving.gold_serving_heatmap_tile_hour",
        "source": "lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min",
        "source_date_sql": "metric_date",
    },
    "queue_hourly": {
        "target": "lakehouse.rva_gold_serving.gold_serving_queue_hourly",
        "source": "lakehouse.rva.gold_queue_sessions_v2",
        "source_date_sql": "CAST(enter_ts AS DATE)",
    },
    "queue_daily": {
        "target": "lakehouse.rva_gold_serving.gold_serving_queue_daily",
        "source": "lakehouse.rva.gold_queue_sessions_v2",
        "source_date_sql": "CAST(enter_ts AS DATE)",
    },
    "zone_hourly": {
        "target": "lakehouse.rva_gold_serving.gold_serving_zone_hourly",
        "source": "lakehouse.rva.silver_detections_v2",
        "source_date_sql": "CAST(capture_ts AS DATE)",
    },
    "zone_daily": {
        "target": "lakehouse.rva_gold_serving.gold_serving_zone_daily",
        "source": "lakehouse.rva.silver_detections_v2",
        "source_date_sql": "CAST(capture_ts AS DATE)",
    },
    "dwell_daily": {
        "target": "lakehouse.rva_gold_serving.gold_serving_dwell_daily",
        "source": "lakehouse.rva.gold_track_summary_v2",
        "source_date_sql": "visit_date",
    },
    "alert_hourly": {
        "target": "lakehouse.rva_gold_serving.gold_serving_alert_hourly",
        "source": "lakehouse.rva.gold_alerts",
        "source_date_sql": "CAST(event_ts AS DATE)",
    },
    "alert_daily": {
        "target": "lakehouse.rva_gold_serving.gold_serving_alert_daily",
        "source": "lakehouse.rva_gold_serving.gold_serving_alert_hourly",
        "source_date_sql": "metric_date",
    },
    "executive_daily": {
        "target": "lakehouse.rva_gold_serving.gold_serving_executive_daily",
        "source": "gold_serving_daily_rollups",
        "source_date_sql": None,
    },
}


def _flink_rest_url() -> str:
    return os.getenv("FLINK_REST_URL", "http://flink-jobmanager:8081").rstrip("/")


def _jar_path() -> Path:
    return Path(os.getenv("FLINK_BATCH_JAR_PATH", "/opt/rva-artifacts/gold-jobs.jar"))


def _lock_path() -> Path:
    return Path(os.getenv("RVA_FLINK_BATCH_LOCK", "/tmp/rva-flink-batch.lock"))


def _sql_string(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _trino_url() -> str:
    return os.getenv("TRINO_URL", "http://localhost:8083").rstrip("/")


def _trino_headers() -> dict[str, str]:
    return {
        "Content-Type": "text/plain",
        "X-Trino-User": os.getenv("TRINO_USER", "rva_gold_serving"),
        "X-Trino-Catalog": os.getenv("TRINO_CATALOG", "lakehouse"),
        "X-Trino-Schema": os.getenv("TRINO_SCHEMA", "rva_gold_serving"),
    }


def _trino_run(sql: str, timeout_sec: int = 120) -> list[list[object]]:
    response = requests.post(
        f"{_trino_url()}/v1/statement",
        data=sql.encode("utf-8"),
        headers=_trino_headers(),
        timeout=timeout_sec,
    )
    response.raise_for_status()
    payload = response.json()
    rows: list[list[object]] = []
    started = time.time()
    while True:
        if payload.get("error"):
            message = payload["error"].get("message", "Trino query failed")
            raise RuntimeError(f"{message} :: {sql[:160].strip()}")
        rows.extend(payload.get("data") or [])
        next_uri = payload.get("nextUri")
        if not next_uri:
            return rows
        if time.time() - started > timeout_sec:
            requests.delete(next_uri, timeout=5)
            raise RuntimeError(f"Timed out waiting for Trino statement :: {sql[:160].strip()}")
        response = requests.get(next_uri, timeout=30)
        response.raise_for_status()
        payload = response.json()


def _trino_scalar(sql: str) -> object:
    rows = _trino_run(sql)
    if rows and rows[0]:
        return rows[0][0]
    return None


def _safe_count(sql: str) -> int | None:
    try:
        value = _trino_scalar(sql)
    except Exception:
        return None
    if value is None:
        return 0
    return int(value)


def _is_missing_table_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "table" in message
        and ("does not exist" in message or "not found" in message)
    )


def _delete_target_window(domain: str, start: str, end: str) -> None:
    spec = DOMAIN_SPECS[domain]
    target = spec["target"]
    sql = (
        f"DELETE FROM {target} "
        f"WHERE metric_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}"
    )
    try:
        _trino_run(sql, timeout_sec=300)
    except Exception as exc:
        if _is_missing_table_error(exc):
            print(f"skip_pre_delete_missing_target domain={domain} table={target}")
            return
        raise


def _write_audit(
    domain: str,
    run_id: str,
    run_mode: str,
    start: str,
    end: str,
    status: str,
    started_at: dt.datetime,
    finished_at: dt.datetime,
    error_message: str | None,
) -> None:
    spec = DOMAIN_SPECS[domain]
    target = spec["target"]
    source = spec["source"]
    window_start = f"{start} 00:00:00.000000"
    window_end = f"{end} 23:59:59.999000"
    output_row_count = _safe_count(
        f"SELECT COUNT(*) FROM {target} "
        f"WHERE metric_date BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}"
    )
    source_row_count = None
    if spec["source_date_sql"] and "." in source:
        source_row_count = _safe_count(
            f"SELECT COUNT(*) FROM {source} "
            f"WHERE {spec['source_date_sql']} BETWEEN DATE {_sql_string(start)} AND DATE {_sql_string(end)}"
        )

    sql = f"""
        INSERT INTO lakehouse.rva_gold_serving.gold_serving_refresh_audit
        SELECT
            'gold_serving_batch',
            {_sql_string(run_id)},
            {_sql_string(run_mode)},
            {_sql_string(target.split('.')[-1])},
            DATE {_sql_string(end)},
            CAST(TIMESTAMP {_sql_string(window_start)} AS TIMESTAMP(6)),
            CAST(TIMESTAMP {_sql_string(window_end)} AS TIMESTAMP(6)),
            {_sql_string(source)},
            {"CAST(NULL AS BIGINT)" if source_row_count is None else str(source_row_count)},
            {"CAST(NULL AS BIGINT)" if output_row_count is None else str(output_row_count)},
            {_sql_string(status)},
            {_sql_string(error_message)},
            CAST(TIMESTAMP {_sql_string(started_at.strftime("%Y-%m-%d %H:%M:%S.%f"))} AS TIMESTAMP(6)),
            CAST(TIMESTAMP {_sql_string(finished_at.strftime("%Y-%m-%d %H:%M:%S.%f"))} AS TIMESTAMP(6)),
            CAST(current_timestamp AS TIMESTAMP(6))
    """
    _trino_run(sql)


def _upload_jar(session: requests.Session, jar_path: Path) -> str:
    with jar_path.open("rb") as fh:
        response = session.post(f"{_flink_rest_url()}/jars/upload", files={"jarfile": fh}, timeout=120)
    if not response.ok:
        raise RuntimeError(
            f"Flink JAR upload failed status={response.status_code}: {response.text[:5000]}"
        )
    payload = response.json()
    filename = payload.get("filename")
    if not filename:
        raise RuntimeError(f"Flink upload response missing filename: {payload}")
    return filename.rsplit("/", 1)[-1]


def _run_job(session: requests.Session, jar_id: str, entry_class: str, program_args: list[str]) -> str:
    response = session.post(
        f"{_flink_rest_url()}/jars/{jar_id}/run",
        json={"entryClass": entry_class, "programArgsList": program_args},
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(
            f"Flink JAR run failed status={response.status_code} "
            f"entry_class={entry_class} jar_id={jar_id}: {response.text[:5000]}"
        )
    payload = response.json()
    job_id = payload.get("jobid")
    if not job_id:
        raise RuntimeError(f"Flink run response missing jobid: {payload}")
    return job_id


def _cancel_job(session: requests.Session, job_id: str) -> None:
    try:
        response = session.patch(
            f"{_flink_rest_url()}/jobs/{job_id}",
            params={"mode": "cancel"},
            timeout=30,
        )
        response.raise_for_status()
    except Exception:
        return


def _wait_for_job(session: requests.Session, job_id: str, poll_sec: int, timeout_sec: int) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        response = session.get(f"{_flink_rest_url()}/jobs/{job_id}", timeout=30)
        response.raise_for_status()
        payload = response.json()
        state = payload.get("state", "UNKNOWN")
        if state == "FINISHED":
            return
        if state in {"FAILED", "CANCELED", "SUSPENDED"}:
            raise RuntimeError(f"Flink batch job {job_id} ended in state {state}: {json.dumps(payload)}")
        time.sleep(poll_sec)
    raise RuntimeError(f"Timed out waiting for Flink batch job {job_id} to finish")


def _delete_uploaded_jar(session: requests.Session, jar_id: str) -> None:
    try:
        session.delete(f"{_flink_rest_url()}/jars/{jar_id}", timeout=30)
    except Exception:
        return


@contextmanager
def _batch_lock(timeout_sec: int):
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with path.open("w") as handle:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() - started > timeout_sec:
                    raise RuntimeError(
                        f"Timed out waiting for batch lock {path} after {timeout_sec}s"
                    )
                time.sleep(5)
        try:
            handle.write(f"{os.getpid()}\n")
            handle.flush()
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--domain",
        required=True,
        choices=[
            "traffic_hourly",
            "traffic_daily",
            "heatmap_5min",
            "heatmap_hour",
            "queue_hourly",
            "queue_daily",
            "zone_hourly",
            "zone_daily",
            "dwell_daily",
            "alert_hourly",
            "alert_daily",
            "executive_daily",
        ],
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--run-mode", default="airflow")
    parser.add_argument("--entry-class", default="org.rva.gold.GoldServingBatchJob")
    parser.add_argument("--poll-sec", type=int, default=5)
    parser.add_argument("--timeout-sec", type=int, default=1800)
    parser.add_argument("--lock-timeout-sec", type=int, default=3600)
    args = parser.parse_args()

    jar_path = _jar_path()
    if not jar_path.exists():
        sys.exit(f"Batch JAR not found: {jar_path}")

    session = requests.Session()
    jar_id = None
    job_id = None
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")[:18]
    started_at = dt.datetime.now(dt.timezone.utc)
    try:
        print(f"waiting_for_lock domain={args.domain} run_id={run_id} lock={_lock_path()}")
        with _batch_lock(args.lock_timeout_sec):
            print(f"acquired_lock domain={args.domain} run_id={run_id}")
            print(
                f"pre_delete_target domain={args.domain} run_id={run_id} "
                f"table={DOMAIN_SPECS[args.domain]['target']} window=[{args.start}..{args.end}]"
            )
            _delete_target_window(args.domain, args.start, args.end)
            jar_id = _upload_jar(session, jar_path)
            program_args = [
                "--domain", args.domain,
                "--start", args.start,
                "--end", args.end,
                "--run-mode", args.run_mode,
            ]
            job_id = _run_job(session, jar_id, args.entry_class, program_args)
            print(f"submitted domain={args.domain} run_id={run_id} job_id={job_id} jar_id={jar_id}")
            _wait_for_job(session, job_id, args.poll_sec, args.timeout_sec)
            finished_at = dt.datetime.now(dt.timezone.utc)
            print(f"finished domain={args.domain} run_id={run_id} job_id={job_id}")
            try:
                _write_audit(
                    domain=args.domain,
                    run_id=run_id,
                    run_mode=args.run_mode,
                    start=args.start,
                    end=args.end,
                    status="ok",
                    started_at=started_at,
                    finished_at=finished_at,
                    error_message=None,
                )
            except Exception as exc:
                print(f"warn audit_write_failed domain={args.domain} run_id={run_id}: {exc}", file=sys.stderr)
    except Exception as exc:
        finished_at = dt.datetime.now(dt.timezone.utc)
        if job_id:
            _cancel_job(session, job_id)
        try:
            _write_audit(
                domain=args.domain,
                run_id=run_id,
                run_mode=args.run_mode,
                start=args.start,
                end=args.end,
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                error_message=str(exc),
            )
        except Exception as audit_exc:
            print(f"warn audit_write_failed domain={args.domain} run_id={run_id}: {audit_exc}", file=sys.stderr)
        raise
    finally:
        if jar_id:
            _delete_uploaded_jar(session, jar_id)


if __name__ == "__main__":
    main()
