#!/bin/bash
# Script tự động submit Flink jobs sau khi JobManager sẵn sàng

set -e

FLINK_HOME=${FLINK_HOME:-/opt/flink}
USR_LIB=${FLINK_USR_LIB_DIR:-/opt/flink/usrlib}

# Hàm đợi JobManager sẵn sàng
wait_for_jobmanager() {
    echo "[submit-jobs] Đợi JobManager khởi động..."
    local max_attempts=60
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf http://flink-jobmanager:8081/overview > /dev/null 2>&1; then
            echo "[submit-jobs] JobManager đã sẵn sàng!"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    echo "[submit-jobs] ERROR: JobManager không khởi động được sau ${max_attempts} lần thử"
    return 1
}

# Hàm submit job với retry
submit_job() {
    local class_name=$1
    local jar_file=$2
    local job_name=$3
    local max_retries=3
    local retry=0
    
    while [ $retry -lt $max_retries ]; do
        echo "[submit-jobs] Submitting ${job_name}..."
        if $FLINK_HOME/bin/flink run -d -c "$class_name" "$jar_file" 2>&1; then
            echo "[submit-jobs] ✓ ${job_name} submitted successfully"
            return 0
        fi
        retry=$((retry + 1))
        echo "[submit-jobs] Retry ${retry}/${max_retries} for ${job_name}..."
        sleep 5
    done
    
    echo "[submit-jobs] ✗ Failed to submit ${job_name}"
    return 1
}

# Main
main() {
    # Đợi JobManager
    wait_for_jobmanager || exit 1
    
    # Đợi thêm 5s để đảm bảo TaskManager đã register
    echo "[submit-jobs] Đợi TaskManager register..."
    sleep 10
    
    # Submit Bronze job
    submit_job "org.rva.BronzeIngestJob" "$USR_LIB/bronze-job.jar" "Bronze"
    sleep 3
    
    # Submit Silver job
    submit_job "org.rva.silver.SilverJob" "$USR_LIB/silver-job.jar" "Silver"
    sleep 3
    
    # Submit 3 Gold jobs (after cleanup - removed zones and duplicate)
    submit_job "org.rva.gold.GoldTrackSummaryJob" "$USR_LIB/gold-jobs.jar" "Gold-TrackSummary"
    # sleep 2
    # submit_job "org.rva.gold.GoldMinuteByCamJob" "$USR_LIB/gold-jobs.jar" "Gold-MinuteByCam"
    # sleep 2
    # submit_job "org.rva.gold.GoldHourByCamJob" "$USR_LIB/gold-jobs.jar" "Gold-HourByCam"
    
    echo "[submit-jobs] ✓ Tất cả jobs đã được submit!"
}

main "$@"
