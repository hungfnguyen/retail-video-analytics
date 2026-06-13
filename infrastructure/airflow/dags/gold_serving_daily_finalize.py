from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

from common import DAG_START, DEFAULT_ARGS, bash_in_runner


with DAG(
    dag_id="gold_serving_daily_finalize",
    description="Finalize yesterday's Gold serving tables.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="0 2 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["rva", "gold-serving", "daily"],
) as dag:
    start = EmptyOperator(task_id="start")

    apply_ddl = BashOperator(
        task_id="apply_gold_serving_ddl",
        bash_command=bash_in_runner("apply_ddl.py"),
        append_env=True,
    )

    refresh_daily = BashOperator(
        task_id="refresh_daily_gold_serving",
        bash_command=bash_in_runner("refresh_runner.py daily --skip-ddl"),
        append_env=True,
    )

    end = EmptyOperator(task_id="end")

    start >> apply_ddl >> refresh_daily >> end
