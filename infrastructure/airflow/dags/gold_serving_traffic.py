from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator

from common import DAG_START, DEFAULT_ARGS, submit_batch_cmd


with DAG(
    dag_id="gold_serving_traffic",
    description="Traffic serving pipeline for one day: traffic_hourly -> traffic_daily.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["rva", "gold-serving", "traffic"],
) as dag:
    refresh_traffic_hourly = BashOperator(
        task_id="refresh_traffic_hourly",
        bash_command=submit_batch_cmd("traffic_hourly", "daily"),
        append_env=True,
    )
    refresh_traffic_daily = BashOperator(
        task_id="refresh_traffic_daily",
        bash_command=submit_batch_cmd("traffic_daily", "daily"),
        append_env=True,
    )

    refresh_traffic_hourly >> refresh_traffic_daily
