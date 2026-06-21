from __future__ import annotations

from datetime import timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

from common import DAG_START, DEFAULT_ARGS, LONG_TASK_TIMEOUT, submit_batch_cmd

# Slower intraday heatmap refresh. It is intentionally decoupled from
# gold_serving_today_refresh because heatmap tiles are heavier than KPI tables.

with DAG(
    dag_id="gold_serving_heatmap_intraday",
    description="Refresh today's heatmap serving tiles every 2 hours.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="0 */2 * * *",
    catchup=False,
    dagrun_timeout=timedelta(minutes=30),
    max_active_runs=1,
    tags=["rva", "gold-serving", "heatmap", "speed-layer"],
) as dag:
    heatmap_5min = BashOperator(
        task_id="heatmap_5min",
        bash_command=submit_batch_cmd("heatmap_5min", "intraday", timeout_sec=900),
        append_env=True,
        execution_timeout=LONG_TASK_TIMEOUT,
    )
    heatmap_hour = BashOperator(
        task_id="heatmap_hour",
        bash_command=submit_batch_cmd("heatmap_hour", "intraday", timeout_sec=900),
        append_env=True,
        execution_timeout=LONG_TASK_TIMEOUT,
    )

    heatmap_5min >> heatmap_hour
