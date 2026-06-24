#!/bin/bash

set -euo pipefail

MODE=${1:-}
if [ -z "${MODE}" ]; then
  echo "[bootstrap-flink] ERROR: expected mode: jobmanager | taskmanager | submitter" >&2
  exit 1
fi

SOURCE_CONF_DIR=/opt/flink/conf
RUNTIME_CONF_DIR=/tmp/flink-conf
CHECKPOINTS_URI=${FLINK_CHECKPOINTS_URI:-}
SAVEPOINTS_URI=${FLINK_SAVEPOINTS_URI:-}

if [ -z "${CHECKPOINTS_URI}" ] || [ -z "${SAVEPOINTS_URI}" ]; then
  echo "[bootstrap-flink] ERROR: FLINK_CHECKPOINTS_URI and FLINK_SAVEPOINTS_URI must be set." >&2
  exit 1
fi

mkdir -p "${RUNTIME_CONF_DIR}"
cp "${SOURCE_CONF_DIR}"/* "${RUNTIME_CONF_DIR}/"

python3 - <<'PY' "${SOURCE_CONF_DIR}/flink-conf.yaml" "${RUNTIME_CONF_DIR}/flink-conf.yaml" "${CHECKPOINTS_URI}" "${SAVEPOINTS_URI}"
import pathlib
import sys

source_path = pathlib.Path(sys.argv[1])
target_path = pathlib.Path(sys.argv[2])
checkpoints = sys.argv[3]
savepoints = sys.argv[4]

content = source_path.read_text(encoding="utf-8")
content = content.replace("__FLINK_CHECKPOINTS_URI__", checkpoints)
content = content.replace("__FLINK_SAVEPOINTS_URI__", savepoints)
target_path.write_text(content, encoding="utf-8")
PY

export FLINK_CONF_DIR="${RUNTIME_CONF_DIR}"
export LOG4J_CONFIGURATION_FILE="${RUNTIME_CONF_DIR}/log4j2.properties"

case "${MODE}" in
  jobmanager|taskmanager)
    exec /docker-entrypoint.sh "${MODE}"
    ;;
  submitter)
    exec /opt/flink/bin/submit-jobs.sh
    ;;
  *)
    echo "[bootstrap-flink] ERROR: unsupported mode '${MODE}'." >&2
    exit 1
    ;;
esac
