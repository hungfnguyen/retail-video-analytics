from __future__ import annotations

from datetime import date

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

from common import DAG_START, DEFAULT_ARGS, bash_in_runner

_TODAY = date.today().isoformat()


with DAG(
    dag_id="gold_serving_backfill",
    description="On-demand backfill of Gold serving tables for a date range.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule=None,  # manual trigger only — set start/end in the trigger form
    catchup=False,
    max_active_runs=1,
    tags=["rva", "gold-serving", "backfill"],
    params={
        "start": Param(_TODAY, type="string", title="Start date (YYYY-MM-DD)"),
        "end": Param(_TODAY, type="string", title="End date (YYYY-MM-DD)"),
    },
) as dag:
    start = EmptyOperator(task_id="start")

    apply_ddl = BashOperator(
        task_id="apply_gold_serving_ddl",
        bash_command=bash_in_runner("apply_ddl.py"),
        append_env=True,
    )

    backfill = BashOperator(
        task_id="backfill_gold_serving",
        bash_command=bash_in_runner(
            "refresh_runner.py backfill --start {{ params.start }} --end {{ params.end }} --skip-ddl"
        ),
        append_env=True,
    )

    end = EmptyOperator(task_id="end")

    start >> apply_ddl >> backfill >> end
