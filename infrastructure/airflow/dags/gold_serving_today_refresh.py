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
    traffic = BashOperator(
        task_id="traffic",
        bash_command=submit_batch_cmd("traffic", "intraday"),
        append_env=True,
    )
    heatmap = BashOperator(
        task_id="heatmap",
        bash_command=submit_batch_cmd("heatmap", "intraday"),
        append_env=True,
    )
    queue = BashOperator(
        task_id="queue",
        bash_command=submit_batch_cmd("queue", "intraday"),
        append_env=True,
    )
    zone = BashOperator(
        task_id="zone",
        bash_command=submit_batch_cmd("zone", "intraday"),
        append_env=True,
    )
    dwell = BashOperator(
        task_id="dwell",
        bash_command=submit_batch_cmd("dwell", "intraday"),
        append_env=True,
    )
    alert = BashOperator(
        task_id="alert",
        bash_command=submit_batch_cmd("alert", "intraday"),
        append_env=True,
    )
    executive = BashOperator(
        task_id="executive",
        bash_command=submit_batch_cmd("executive", "intraday"),
        append_env=True,
    )

    traffic >> heatmap >> queue >> zone >> dwell >> alert >> executive
