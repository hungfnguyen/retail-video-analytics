#!/usr/bin/env bash
set -euo pipefail

TENANT="retail"
NAMESPACE="${TENANT}/metadata"
TOPIC="persistent://${NAMESPACE}/events"
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

# 3. Set retention (lưu trữ)
/pulsar/bin/pulsar-admin namespaces set-retention "${NAMESPACE}" \
  --size -1 --time -1 >/dev/null 2>&1

# 4. Cleanup topic cũ (Xóa cả partitioned và non-partitioned để chắc chắn)
/pulsar/bin/pulsar-admin topics delete-partitioned-topic "${TOPIC}" \
  --force >/dev/null 2>&1 || true

/pulsar/bin/pulsar-admin topics delete "${TOPIC}" \
  --force >/dev/null 2>&1 || true

/pulsar/bin/pulsar-admin schemas delete "${TOPIC}" \
  >/dev/null 2>&1 || true

# 5. [QUAN TRỌNG] Tạo PARTITIONED topic (Thay đổi ở đây)
# Flink SQL Connector 1.18 yêu cầu partitioned topic để hoạt động ổn định
echo "[init] Creating partitioned topic ${TOPIC}..."
/pulsar/bin/pulsar-admin topics create-partitioned-topic "${TOPIC}" -p 1 \
  >/dev/null 2>&1 || true

# 6. Upload Schema
if [ -f "${SCHEMA_PATH}" ]; then
  echo "[init] Uploading schema from ${SCHEMA_PATH}"
  /pulsar/bin/pulsar-admin schemas upload "${TOPIC}" \
    --filename "${SCHEMA_PATH}" >/dev/null 2>&1
fi

echo "[init] Done"