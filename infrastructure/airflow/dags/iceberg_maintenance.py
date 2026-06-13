from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

from common import DAG_START, DEFAULT_ARGS, bash_in_runner


with DAG(
    dag_id="iceberg_maintenance",
    description="Run periodic Iceberg OPTIMIZE and lightweight DQ checks.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="0 */6 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["rva", "iceberg", "maintenance"],
) as dag:
    start = EmptyOperator(task_id="start")

    optimize_tables = BashOperator(
        task_id="optimize_hot_tables",
        bash_command=bash_in_runner("maintenance.py"),
        append_env=True,
    )

    end = EmptyOperator(task_id="end")

    start >> optimize_tables >> end
