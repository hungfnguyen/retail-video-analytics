#!/usr/bin/env bash
# Snapshot tất cả container logs ra thư mục logs/ kèm timestamp.
# Dùng để debug offline hoặc đính kèm báo cáo đồ án.
set -euo pipefail

TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
SNAPSHOT_DIR="logs/snapshot_${TIMESTAMP}"
mkdir -p "${SNAPSHOT_DIR}"

CONTAINERS=(
    pulsar-broker
    pulsar-init
    flink-jobmanager
    flink-taskmanager
    flink-job-submitter
    redis
    iceberg-rest
    trino
)

echo "=== Snapshot logs → ${SNAPSHOT_DIR} ==="

for container in "${CONTAINERS[@]}"; do
    if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -n "  ${container} ... "
        docker logs "${container}" > "${SNAPSHOT_DIR}/${container}.log" 2>&1
        echo "$(wc -l < "${SNAPSHOT_DIR}/${container}.log") lines"
    else
        echo "  ${container} → SKIP (not found)"
    fi
done

# Tạo symlink latest → snapshot mới nhất
ln -sfn "snapshot_${TIMESTAMP}" logs/latest

echo "=== Done: logs/latest/ ==="
ls -la logs/latest/
