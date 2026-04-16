#!/bin/bash

set -euo pipefail

ALIAS_NAME="${MINIO_MC_ALIAS:-local}"
SERVER_URL="${MINIO_SERVER_URL:-http://minio:9000}"
ACCESS_KEY="${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
SECRET_KEY="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"
WAREHOUSE_URI="${ICEBERG_WAREHOUSE:-s3a://warehouse}"
EXTRA_BUCKETS="${MINIO_ADDITIONAL_BUCKETS:-}"

normalize_bucket() {
  local uri="$1"
  uri="${uri#s3a://}"
  uri="${uri#s3://}"
  uri="${uri#/}"
  echo "${uri%%/*}"
}

WAREHOUSE_BUCKET="$(normalize_bucket "${WAREHOUSE_URI}")"
if [[ -z "${WAREHOUSE_BUCKET}" ]]; then
  echo "[minio-init] Unable to determine bucket name from ICEBERG_WAREHOUSE='${WAREHOUSE_URI}'" >&2
  exit 1
fi

configure_alias() {
  until mc alias set "${ALIAS_NAME}" "${SERVER_URL}" "${ACCESS_KEY}" "${SECRET_KEY}" >/dev/null 2>&1; do
    echo "[minio-init] Waiting for MinIO API..."
    sleep 2
  done
}

wait_until_ready() {
  until mc ready "${ALIAS_NAME}" >/dev/null 2>&1; do
    echo "[minio-init] Waiting for MinIO server..."
    sleep 2
  done
}

create_bucket() {
  local bucket="$1"
  if [[ -z "${bucket}" ]]; then
    return
  fi
  echo "[minio-init] Ensuring bucket '${bucket}' exists"
  mc mb "${ALIAS_NAME}/${bucket}" --ignore-existing >/dev/null 2>&1 || true
}

echo "[minio-init] Configuring alias '${ALIAS_NAME}' for ${SERVER_URL}"
configure_alias

wait_until_ready

echo "[minio-init] Creating required buckets"
create_bucket "${WAREHOUSE_BUCKET}"

for bucket in ${EXTRA_BUCKETS}; do
  create_bucket "${bucket}"
done

echo "[minio-init] Current buckets:"
mc ls "${ALIAS_NAME}" || true
