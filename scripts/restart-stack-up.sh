#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AIRFLOW_SERVICE="${AIRFLOW_SERVICE:-airflow}"
AIRFLOW_DAG_ID="${AIRFLOW_DAG_ID:-gold_serving_today_refresh}"
WAIT_TIMEOUT_SEC="${WAIT_TIMEOUT_SEC:-300}"
RUN_ID="manual__startup__$(date -u +%Y%m%dT%H%M%SZ)"

cd "${PROJECT_ROOT}"
mkdir -p runtime/flink

echo "[restart-up] Starting Docker stack..."
docker compose up -d --build

echo "[restart-up] Waiting for Airflow CLI to become ready..."
deadline=$((SECONDS + WAIT_TIMEOUT_SEC))
until docker compose exec -T "${AIRFLOW_SERVICE}" airflow dags list >/dev/null 2>&1; do
  if [ "${SECONDS}" -ge "${deadline}" ]; then
    echo "[restart-up] ERROR: Airflow did not become ready within ${WAIT_TIMEOUT_SEC}s." >&2
    exit 1
  fi
  sleep 5
done

echo "[restart-up] Unpausing ${AIRFLOW_DAG_ID}..."
docker compose exec -T "${AIRFLOW_SERVICE}" airflow dags unpause "${AIRFLOW_DAG_ID}" >/dev/null

echo "[restart-up] Triggering ${AIRFLOW_DAG_ID} with run id ${RUN_ID}..."
docker compose exec -T "${AIRFLOW_SERVICE}" airflow dags trigger "${AIRFLOW_DAG_ID}" --run-id "${RUN_ID}" >/dev/null

echo "[restart-up] Stack is up. Start Vision separately when ready."
