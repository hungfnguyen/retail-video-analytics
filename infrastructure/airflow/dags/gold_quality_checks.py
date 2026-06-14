from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

from common import DAG_START, DEFAULT_ARGS, bash_in_runner


with DAG(
    dag_id="gold_quality_checks",
    description="Freshness + non-negative + today-presence checks on the Gold serving layer.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="0 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["rva", "gold-serving", "quality"],
) as dag:
    start = EmptyOperator(task_id="start")

    # Writes results into gold_serving_data_quality_results and exits non-zero on
    # any error-level check, so this task fails (and can alert) on real problems.
    quality = BashOperator(
        task_id="run_quality_checks",
        bash_command=bash_in_runner("quality_checks.py"),
        append_env=True,
    )

    end = EmptyOperator(task_id="end")

    start >> quality >> end
