#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRY_PATH="${PROJECT_ROOT}/runtime/flink/job-registry.tsv"
MANIFEST_PATH="${PROJECT_ROOT}/runtime/flink/restore-manifest.tsv"
WAIT_TIMEOUT_SEC="${WAIT_TIMEOUT_SEC:-300}"

cd "${PROJECT_ROOT}"
mkdir -p runtime/flink

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

SAVEPOINT_TARGET_DIR="${FLINK_SAVEPOINTS_URI:-}"
if [ -z "${SAVEPOINT_TARGET_DIR}" ]; then
  echo "[restart-down] ERROR: FLINK_SAVEPOINTS_URI must be set in the environment or .env." >&2
  exit 1
fi

if ! docker compose ps --status running | grep -q "flink-jobmanager"; then
  echo "[restart-down] Flink stack is not running. Stopping compose services only."
  rm -f "${MANIFEST_PATH}"
  docker compose down
  exit 0
fi

if [ ! -f "${REGISTRY_PATH}" ]; then
  echo "[restart-down] No job registry found at ${REGISTRY_PATH}. Proceeding without savepoints."
  rm -f "${MANIFEST_PATH}"
  docker compose down
  exit 0
fi

: > "${MANIFEST_PATH}"

request_savepoint() {
  local job_id=$1
  local response
  response=$(curl -fsS -X POST "http://localhost:8081/jobs/${job_id}/savepoints" \
    -H "Content-Type: application/json" \
    -d "{\"target-directory\":\"${SAVEPOINT_TARGET_DIR}\",\"cancel-job\":false}")
  python3 -c 'import json,sys; print(json.load(sys.stdin)["request-id"])' <<<"${response}"
}

poll_savepoint() {
  local job_id=$1
  local trigger_id=$2
  python3 - "${job_id}" "${trigger_id}" "${WAIT_TIMEOUT_SEC}" <<'PY'
import json
import sys
import time
from urllib.request import urlopen

job_id, trigger_id, wait_timeout = sys.argv[1], sys.argv[2], int(sys.argv[3])
deadline = time.time() + wait_timeout
url = f"http://localhost:8081/jobs/{job_id}/savepoints/{trigger_id}"

while time.time() < deadline:
    with urlopen(url, timeout=5) as response:
        payload = json.load(response)
    status = ((payload.get("status") or {}).get("id") or "").upper()
    operation = payload.get("operation") or {}
    if status == "COMPLETED":
        location = operation.get("location")
        if location:
            print(location)
            sys.exit(0)
        print("completed-without-location", file=sys.stderr)
        sys.exit(1)
    if status == "FAILED":
        print(operation.get("failure-cause", "savepoint failed"), file=sys.stderr)
        sys.exit(1)
    time.sleep(3)

print("savepoint timeout", file=sys.stderr)
sys.exit(1)
PY
}

while IFS='|' read -r class_name job_name job_id stateful; do
  if [ "${stateful}" != "true" ] || [ -z "${job_id}" ]; then
    continue
  fi

  echo "[restart-down] Creating savepoint for ${job_name} (${job_id})..."
  if ! trigger_id=$(request_savepoint "${job_id}"); then
    echo "[restart-down] WARN: failed to request savepoint for ${job_name}." >&2
    continue
  fi

  if ! savepoint_path=$(poll_savepoint "${job_id}" "${trigger_id}"); then
    echo "[restart-down] WARN: savepoint did not complete for ${job_name}." >&2
    continue
  fi

  printf '%s|%s\n' "${class_name}" "${savepoint_path}" >> "${MANIFEST_PATH}"
  echo "[restart-down] Savepoint recorded: ${class_name} -> ${savepoint_path}"
done < "${REGISTRY_PATH}"

echo "[restart-down] Stopping Docker stack..."
docker compose down
