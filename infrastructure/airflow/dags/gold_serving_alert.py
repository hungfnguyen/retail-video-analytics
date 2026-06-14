from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator

from common import DAG_START, DEFAULT_ARGS, submit_batch_cmd


with DAG(
    dag_id="gold_serving_alert",
    description="Alert serving pipeline for one day: alert_hourly -> alert_daily (from gold_alerts).",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["rva", "gold-serving", "alert"],
) as dag:
    refresh_alert = BashOperator(
        task_id="refresh_alert",
        bash_command=submit_batch_cmd("alert", "daily"),
        append_env=True,
    )

    refresh_alert
