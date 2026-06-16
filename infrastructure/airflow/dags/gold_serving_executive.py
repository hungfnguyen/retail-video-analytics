from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.sensors.external_task import ExternalTaskSensor

from common import DAG_START, DEFAULT_ARGS, submit_batch_cmd

# executive_daily rolls up traffic_daily + dwell/queue/alert daily grains, so it
# must wait for those domain pipelines to finish the SAME logical day.
UPSTREAMS = {
    "wait_traffic": ("gold_serving_traffic", "refresh_traffic_daily"),
    "wait_dwell": ("gold_serving_dwell", "refresh_dwell"),
    "wait_queue": ("gold_serving_queue", "refresh_queue_daily"),
    "wait_alert": ("gold_serving_alert", "refresh_alert_daily"),
}


with DAG(
    dag_id="gold_serving_executive",
    description="Executive daily rollup; waits for upstream domain pipelines at the same logical date.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["rva", "gold-serving", "executive"],
) as dag:
    waits = [
        ExternalTaskSensor(
            task_id=task_id,
            external_dag_id=external_dag_id,
            external_task_id=external_task_id,
            allowed_states=["success"],
            failed_states=["failed", "upstream_failed"],
            mode="reschedule",  # free the slot between pokes (required under SequentialExecutor)
            poke_interval=30,
            timeout=60 * 60,
        )
        for task_id, (external_dag_id, external_task_id) in UPSTREAMS.items()
    ]

    refresh_executive = BashOperator(
        task_id="refresh_executive",
        bash_command=submit_batch_cmd("executive_daily", "daily"),
        append_env=True,
    )

    waits >> refresh_executive
