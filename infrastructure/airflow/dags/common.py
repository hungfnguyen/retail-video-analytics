from __future__ import annotations

import os
from datetime import datetime, timedelta


PROJECT_ROOT = os.getenv("RVA_PROJECT_ROOT", "/opt/retail-video-analytics")
PYTHON_BIN = os.getenv("RVA_PYTHON_BIN", "/usr/bin/python3")
SERVING_RUNNER_DIR = os.getenv("RVA_SERVING_RUNNER_DIR", os.path.join(PROJECT_ROOT, "services", "gold_serving"))
FLINK_BATCH_SUBMITTER = os.getenv(
    "RVA_FLINK_BATCH_SUBMITTER",
    os.path.join(PROJECT_ROOT, "services", "flink-jobs", "python", "submit_batch_job.py"),
)


def bash_in_runner(script_and_args: str) -> str:
    return f"cd {SERVING_RUNNER_DIR} && {PYTHON_BIN} {script_and_args}"


DEFAULT_TASK_TIMEOUT = timedelta(minutes=12)
LONG_TASK_TIMEOUT = timedelta(minutes=20)


def submit_batch_cmd(domain: str, run_mode: str = "airflow", timeout_sec: int | None = None) -> str:
    timeout_arg = f" --timeout-sec {timeout_sec}" if timeout_sec is not None else ""
    return (
        f"{PYTHON_BIN} {FLINK_BATCH_SUBMITTER} "
        f"--domain {domain} --start {{{{ ds }}}} --end {{{{ ds }}}} --run-mode {run_mode}"
        f"{timeout_arg}"
    )


DEFAULT_ARGS = {
    "owner": "rva",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}


DAG_START = datetime(2026, 6, 12)
