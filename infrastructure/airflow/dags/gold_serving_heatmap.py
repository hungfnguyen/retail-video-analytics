from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator

from common import DAG_START, DEFAULT_ARGS, submit_batch_cmd


with DAG(
    dag_id="gold_serving_heatmap",
    description="Heatmap serving pipeline for one day: heatmap_tile_5min -> heatmap_tile_hour.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["rva", "gold-serving", "heatmap"],
) as dag:
    refresh_heatmap_5min = BashOperator(
        task_id="refresh_heatmap_5min",
        bash_command=submit_batch_cmd("heatmap_5min", "daily"),
        append_env=True,
    )
    refresh_heatmap_hour = BashOperator(
        task_id="refresh_heatmap_hour",
        bash_command=submit_batch_cmd("heatmap_hour", "daily"),
        append_env=True,
    )

    refresh_heatmap_5min >> refresh_heatmap_hour
