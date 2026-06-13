from __future__ import annotations

import os
from datetime import datetime


PROJECT_ROOT = os.getenv("RVA_PROJECT_ROOT", "/opt/retail-video-analytics")
PYTHON_BIN = os.getenv("RVA_PYTHON_BIN", "/usr/bin/python3")
SERVING_RUNNER_DIR = os.getenv(
    "RVA_SERVING_RUNNER_DIR",
    os.path.join(PROJECT_ROOT, "services", "gold_serving"),
)


def bash_in_runner(script_and_args: str) -> str:
    return f"cd {SERVING_RUNNER_DIR} && {PYTHON_BIN} {script_and_args}"


DEFAULT_ARGS = {
    "owner": "rva",
    "depends_on_past": False,
    "retries": 1,
}


DAG_START = datetime(2026, 6, 12)
