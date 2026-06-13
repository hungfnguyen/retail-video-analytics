from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator

from common import DAG_START, DEFAULT_ARGS, submit_batch_cmd


with DAG(
    dag_id="gold_serving_dwell",
    description="Dwell serving pipeline for one day: dwell_daily (from gold_track_summary_v2).",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["rva", "gold-serving", "dwell"],
) as dag:
    refresh_dwell = BashOperator(
        task_id="refresh_dwell",
        bash_command=submit_batch_cmd("dwell", "daily"),
        append_env=True,
    )

    refresh_dwell
