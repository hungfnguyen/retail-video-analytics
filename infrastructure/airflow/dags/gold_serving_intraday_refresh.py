from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

from common import DAG_START, DEFAULT_ARGS, bash_in_runner


with DAG(
    dag_id="gold_serving_intraday_refresh",
    description="Refresh intraday Gold serving tables from Silver/Gold facts.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="*/15 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["rva", "gold-serving", "intraday"],
) as dag:
    start = EmptyOperator(task_id="start")

    apply_ddl = BashOperator(
        task_id="apply_gold_serving_ddl",
        bash_command=bash_in_runner("apply_ddl.py"),
        append_env=True,
    )

    refresh_intraday = BashOperator(
        task_id="refresh_intraday_gold_serving",
        bash_command=bash_in_runner("refresh_runner.py intraday --skip-ddl"),
        append_env=True,
    )

    end = EmptyOperator(task_id="end")

    start >> apply_ddl >> refresh_intraday >> end
