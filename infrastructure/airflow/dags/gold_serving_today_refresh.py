from __future__ import annotations

from airflow import DAG
from airflow.operators.bash import BashOperator

from common import DAG_START, DEFAULT_ARGS, submit_batch_cmd

# Speed layer: keeps TODAY's serving partition warm so the dashboard is live,
# without waiting for the @daily per-domain pipelines (which only finalize a day
# once its interval has closed, i.e. fresh T-1). This is operational glue, not a
# domain workflow, so it stays monolithic: one run refreshes all serving tables
# for the current date via the runner's `intraday` mode (window = today).
# catchup=False — there is no per-interval history to fill; it only ever warms today.

with DAG(
    dag_id="gold_serving_today_refresh",
    description="Speed layer: refresh today's Gold serving partition every 30 min for a live dashboard.",
    default_args=DEFAULT_ARGS,
    start_date=DAG_START,
    schedule="*/30 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["rva", "gold-serving", "speed-layer"],
) as dag:
    traffic_hourly = BashOperator(
        task_id="traffic_hourly",
        bash_command=submit_batch_cmd("traffic_hourly", "intraday"),
        append_env=True,
    )
    traffic_daily = BashOperator(
        task_id="traffic_daily",
        bash_command=submit_batch_cmd("traffic_daily", "intraday"),
        append_env=True,
    )
    heatmap_5min = BashOperator(
        task_id="heatmap_5min",
        bash_command=submit_batch_cmd("heatmap_5min", "intraday"),
        append_env=True,
    )
    heatmap_hour = BashOperator(
        task_id="heatmap_hour",
        bash_command=submit_batch_cmd("heatmap_hour", "intraday"),
        append_env=True,
    )
    queue_hourly = BashOperator(
        task_id="queue_hourly",
        bash_command=submit_batch_cmd("queue_hourly", "intraday"),
        append_env=True,
    )
    queue_daily = BashOperator(
        task_id="queue_daily",
        bash_command=submit_batch_cmd("queue_daily", "intraday"),
        append_env=True,
    )
    zone_hourly = BashOperator(
        task_id="zone_hourly",
        bash_command=submit_batch_cmd("zone_hourly", "intraday"),
        append_env=True,
    )
    zone_daily = BashOperator(
        task_id="zone_daily",
        bash_command=submit_batch_cmd("zone_daily", "intraday"),
        append_env=True,
    )
    dwell_daily = BashOperator(
        task_id="dwell_daily",
        bash_command=submit_batch_cmd("dwell_daily", "intraday"),
        append_env=True,
    )
    alert_hourly = BashOperator(
        task_id="alert_hourly",
        bash_command=submit_batch_cmd("alert_hourly", "intraday"),
        append_env=True,
    )
    alert_daily = BashOperator(
        task_id="alert_daily",
        bash_command=submit_batch_cmd("alert_daily", "intraday"),
        append_env=True,
    )
    executive_daily = BashOperator(
        task_id="executive_daily",
        bash_command=submit_batch_cmd("executive_daily", "intraday"),
        append_env=True,
    )

    traffic_hourly >> traffic_daily >> heatmap_5min >> heatmap_hour >> queue_hourly >> queue_daily >> zone_hourly >> zone_daily >> dwell_daily >> alert_hourly >> alert_daily >> executive_daily
