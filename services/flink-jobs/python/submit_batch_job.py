#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests


def _flink_rest_url() -> str:
    return os.getenv("FLINK_REST_URL", "http://flink-jobmanager:8081").rstrip("/")


def _jar_path() -> Path:
    return Path(os.getenv("FLINK_BATCH_JAR_PATH", "/opt/rva-artifacts/gold-jobs.jar"))


def _upload_jar(session: requests.Session, jar_path: Path) -> str:
    with jar_path.open("rb") as fh:
        response = session.post(f"{_flink_rest_url()}/jars/upload", files={"jarfile": fh}, timeout=120)
    response.raise_for_status()
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
    response.raise_for_status()
    payload = response.json()
    job_id = payload.get("jobid")
    if not job_id:
        raise RuntimeError(f"Flink run response missing jobid: {payload}")
    return job_id


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
    args = parser.parse_args()

    jar_path = _jar_path()
    if not jar_path.exists():
        sys.exit(f"Batch JAR not found: {jar_path}")

    session = requests.Session()
    jar_id = None
    try:
        jar_id = _upload_jar(session, jar_path)
        program_args = [
            "--domain", args.domain,
            "--start", args.start,
            "--end", args.end,
            "--run-mode", args.run_mode,
        ]
        job_id = _run_job(session, jar_id, args.entry_class, program_args)
        print(f"submitted domain={args.domain} job_id={job_id} jar_id={jar_id}")
        _wait_for_job(session, job_id, args.poll_sec, args.timeout_sec)
        print(f"finished domain={args.domain} job_id={job_id}")
    finally:
        if jar_id:
            _delete_uploaded_jar(session, jar_id)


if __name__ == "__main__":
    main()
