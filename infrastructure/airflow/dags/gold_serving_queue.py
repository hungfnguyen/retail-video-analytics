from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator

from common import DAG_START, DEFAULT_ARGS, submit_batch_cmd


with DAG(
    dag_id="gold_serving_queue",
    description="Queue serving pipeline for one day: queue_hourly + queue_daily (both from gold_queue_sessions).",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["rva", "gold-serving", "queue"],
) as dag:
    refresh_queue = BashOperator(
        task_id="refresh_queue",
        bash_command=submit_batch_cmd("queue", "daily"),
        append_env=True,
    )

    refresh_queue
