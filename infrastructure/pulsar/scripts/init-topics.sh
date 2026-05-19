#!/usr/bin/env bash
set -euo pipefail

TENANT="retail"
NAMESPACE="${TENANT}/metadata"
TOPIC="persistent://${NAMESPACE}/events"
MEDIA_TOPIC="persistent://${NAMESPACE}/media-events"
DLQ_TOPIC="persistent://${NAMESPACE}/dlq-events"
SCHEMA_PATH="/pulsar/schema/metadata-json-schema.json"

echo "[init] Waiting for Pulsar..."
until /pulsar/bin/pulsar-admin brokers healthcheck >/dev/null 2>&1; do
  sleep 2
done

# 1. Tạo Tenant
/pulsar/bin/pulsar-admin tenants create "${TENANT}" \
  --allowed-clusters standalone >/dev/null 2>&1 || true

# 2. Tạo Namespace
/pulsar/bin/pulsar-admin namespaces create "${NAMESPACE}" \
  >/dev/null 2>&1 || true

# 3. Set schema policy
# Phase 1: register schema in Pulsar, but keep validation disabled because
# Python Vision still publishes raw JSON bytes. Producer-side schema enforcement
# belongs to the next migration phase.
/pulsar/bin/pulsar-admin namespaces set-schema-compatibility-strategy \
  --compatibility BACKWARD "${NAMESPACE}"

/pulsar/bin/pulsar-admin namespaces set-schema-validation-enforce \
  --disable "${NAMESPACE}"

# 4. Set retention (lưu trữ)
/pulsar/bin/pulsar-admin namespaces set-retention "${NAMESPACE}" \
  --size -1 --time -1 >/dev/null 2>&1

# 5. Cleanup topic cũ (Xóa cả partitioned và non-partitioned để chắc chắn)
/pulsar/bin/pulsar-admin topics delete-partitioned-topic "${TOPIC}" \
  --force >/dev/null 2>&1 || true

/pulsar/bin/pulsar-admin topics delete "${TOPIC}" \
  --force >/dev/null 2>&1 || true

/pulsar/bin/pulsar-admin schemas delete "${TOPIC}" \
  >/dev/null 2>&1 || true

/pulsar/bin/pulsar-admin topics delete-partitioned-topic "${MEDIA_TOPIC}" \
  --force >/dev/null 2>&1 || true

/pulsar/bin/pulsar-admin topics delete "${MEDIA_TOPIC}" \
  --force >/dev/null 2>&1 || true

# 6. [QUAN TRỌNG] Tạo PARTITIONED topic
# Số partition = số camera để mỗi camera có ordering riêng qua partition_key
EVENTS_PARTITIONS="${PULSAR_EVENTS_PARTITIONS:-2}"

echo "[init] Creating partitioned topic ${TOPIC} (${EVENTS_PARTITIONS} partitions)..."
/pulsar/bin/pulsar-admin topics create-partitioned-topic "${TOPIC}" -p "${EVENTS_PARTITIONS}" \
  >/dev/null 2>&1 || true

echo "[init] Creating partitioned topic ${MEDIA_TOPIC}..."
/pulsar/bin/pulsar-admin topics create-partitioned-topic "${MEDIA_TOPIC}" -p 1 \
  >/dev/null 2>&1 || true

# Delete DLQ topic nếu tồn tại
/pulsar/bin/pulsar-admin topics delete-partitioned-topic "${DLQ_TOPIC}" \
  --force >/dev/null 2>&1 || true
/pulsar/bin/pulsar-admin topics delete "${DLQ_TOPIC}" \
  --force >/dev/null 2>&1 || true

echo "[init] Creating partitioned topic ${DLQ_TOPIC}..."
/pulsar/bin/pulsar-admin topics create-partitioned-topic "${DLQ_TOPIC}" -p 1 \
  >/dev/null 2>&1 || true

# 7. Upload Schema
if [ -f "${SCHEMA_PATH}" ]; then
  echo "[init] Uploading schema from ${SCHEMA_PATH}..."
  /pulsar/bin/pulsar-admin schemas upload "${TOPIC}" \
    --filename "${SCHEMA_PATH}"
fi

echo "[init] Topics created successfully"
