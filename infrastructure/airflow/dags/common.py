from __future__ import annotations

import os
from datetime import datetime


PROJECT_ROOT = os.getenv("RVA_PROJECT_ROOT", "/opt/retail-video-analytics")
PYTHON_BIN = os.getenv("RVA_PYTHON_BIN", "/usr/bin/python3")
SERVING_RUNNER_DIR = os.getenv("RVA_SERVING_RUNNER_DIR", os.path.join(PROJECT_ROOT, "services", "gold_serving"))
FLINK_BATCH_SUBMITTER = os.getenv(
    "RVA_FLINK_BATCH_SUBMITTER",
    os.path.join(PROJECT_ROOT, "services", "flink-jobs", "python", "submit_batch_job.py"),
)


def bash_in_runner(script_and_args: str) -> str:
    return f"cd {SERVING_RUNNER_DIR} && {PYTHON_BIN} {script_and_args}"


def submit_batch_cmd(domain: str, run_mode: str = "airflow") -> str:
    return (
        f"{PYTHON_BIN} {FLINK_BATCH_SUBMITTER} "
        f"--domain {domain} --start {{{{ ds }}}} --end {{{{ ds }}}} --run-mode {run_mode}"
    )


DEFAULT_ARGS = {
    "owner": "rva",
    "depends_on_past": False,
    "retries": 1,
}


DAG_START = datetime(2026, 6, 12)
