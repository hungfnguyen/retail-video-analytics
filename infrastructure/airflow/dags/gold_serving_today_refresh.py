from __future__ import annotations

from datetime import timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

from common import DAG_START, DEFAULT_ARGS, DEFAULT_TASK_TIMEOUT, LONG_TASK_TIMEOUT, submit_batch_cmd

# Speed layer for today's Analytics-facing serving tables. Heatmap tiles run in
# a separate DAG so heavier spatial refreshes cannot block KPI refresh.

with DAG(
    dag_id="gold_serving_today_refresh",
    description="Speed layer: refresh today's Analytics Gold serving partition every 30 min.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="*/30 * * * *",
    catchup=False,
    dagrun_timeout=timedelta(minutes=20),
    max_active_runs=1,
    tags=["rva", "gold-serving", "speed-layer"],
) as dag:
    traffic_hourly = BashOperator(
        task_id="traffic_hourly",
        bash_command=submit_batch_cmd("traffic_hourly", "intraday", timeout_sec=600),
        append_env=True,
        execution_timeout=DEFAULT_TASK_TIMEOUT,
    )
    traffic_daily = BashOperator(
        task_id="traffic_daily",
        bash_command=submit_batch_cmd("traffic_daily", "intraday", timeout_sec=600),
        append_env=True,
        execution_timeout=DEFAULT_TASK_TIMEOUT,
    )
    queue_hourly = BashOperator(
        task_id="queue_hourly",
        bash_command=submit_batch_cmd("queue_hourly", "intraday", timeout_sec=600),
        append_env=True,
        execution_timeout=DEFAULT_TASK_TIMEOUT,
    )
    queue_daily = BashOperator(
        task_id="queue_daily",
        bash_command=submit_batch_cmd("queue_daily", "intraday", timeout_sec=600),
        append_env=True,
        execution_timeout=DEFAULT_TASK_TIMEOUT,
    )
    zone_hourly = BashOperator(
        task_id="zone_hourly",
        bash_command=submit_batch_cmd("zone_hourly", "intraday", timeout_sec=600),
        append_env=True,
        execution_timeout=DEFAULT_TASK_TIMEOUT,
    )
    zone_daily = BashOperator(
        task_id="zone_daily",
        bash_command=submit_batch_cmd("zone_daily", "intraday", timeout_sec=600),
        append_env=True,
        execution_timeout=DEFAULT_TASK_TIMEOUT,
    )
    dwell_daily = BashOperator(
        task_id="dwell_daily",
        bash_command=submit_batch_cmd("dwell_daily", "intraday", timeout_sec=600),
        append_env=True,
        execution_timeout=DEFAULT_TASK_TIMEOUT,
    )
    alert_hourly = BashOperator(
        task_id="alert_hourly",
        bash_command=submit_batch_cmd("alert_hourly", "intraday", timeout_sec=600),
        append_env=True,
        execution_timeout=DEFAULT_TASK_TIMEOUT,
    )
    alert_daily = BashOperator(
        task_id="alert_daily",
        bash_command=submit_batch_cmd("alert_daily", "intraday", timeout_sec=600),
        append_env=True,
        execution_timeout=DEFAULT_TASK_TIMEOUT,
    )
    executive_daily = BashOperator(
        task_id="executive_daily",
        bash_command=submit_batch_cmd("executive_daily", "intraday", timeout_sec=900),
        append_env=True,
        execution_timeout=LONG_TASK_TIMEOUT,
    )

    traffic_hourly >> traffic_daily >> queue_hourly >> queue_daily >> zone_hourly >> zone_daily >> dwell_daily >> alert_hourly >> alert_daily >> executive_daily
