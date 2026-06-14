from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator

from common import DAG_START, DEFAULT_ARGS, submit_batch_cmd


with DAG(
    dag_id="gold_serving_zone",
    description="Zone serving pipeline for one day: zone_hourly + zone_daily (both from silver_detections_v2).",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["rva", "gold-serving", "zone"],
) as dag:
    refresh_zone = BashOperator(
        task_id="refresh_zone",
        bash_command=submit_batch_cmd("zone", "daily"),
        append_env=True,
    )

    refresh_zone
