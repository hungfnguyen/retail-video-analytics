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

# Hàm kiểm tra job status bằng tên
check_job_status() {
    local job_name=$1
    local max_wait=60
    local attempt=0
    
    echo "[submit-jobs] Checking status of job: ${job_name}..."
    
    while [ $attempt -lt $max_wait ]; do
        # Lấy danh sách jobs từ Flink REST API
        local response=$(curl -sf http://flink-jobmanager:8081/jobs 2>/dev/null)
        
        if [ -z "$response" ]; then
            echo "[submit-jobs] Cannot fetch job list, retrying..."
            sleep 2
            attempt=$((attempt + 1))
            continue
        fi
        
        # Tìm job ID theo tên (giả sử job có name trong metadata)
        # Kiểm tra xem có job nào RUNNING không
        local running_count=$(echo "$response" | grep -o '"status":"RUNNING"' | wc -l)
        
        if [ "$running_count" -gt 0 ]; then
            echo "[submit-jobs] ✓ Job ${job_name} is now RUNNING"
            return 0
        fi
        
        # Nếu có job FAILED, báo lỗi ngay
        local failed_count=$(echo "$response" | grep -o '"status":"FAILED"' | wc -l)
        if [ "$failed_count" -gt 0 ]; then
            echo "[submit-jobs] ✗ Detected FAILED job!"
            return 1
        fi
        
        attempt=$((attempt + 1))
        sleep 2
    done
    
    echo "[submit-jobs] ⚠ Timeout waiting for job ${job_name} to be RUNNING"
    return 1
}

# Hàm submit job với retry và status check
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
            
            # Đợi job chuyển sang RUNNING
            if check_job_status "$job_name"; then
                return 0
            else
                echo "[submit-jobs] Job ${job_name} không chuyển sang RUNNING, có thể bị lỗi"
                retry=$((retry + 1))
                continue
            fi
        fi
        retry=$((retry + 1))
        echo "[submit-jobs] Retry ${retry}/${max_retries} for ${job_name}..."
        sleep 5
    done
    
    echo "[submit-jobs] ✗ Failed to submit ${job_name} after ${max_retries} attempts"
    return 1
}

# Main
main() {
    # Đợi JobManager
    wait_for_jobmanager || exit 1
    
    # Đợi thêm để đảm bảo TaskManager đã register
    echo "[submit-jobs] Đợi TaskManager register..."
    sleep 10
    
    # Submit Bronze job và đợi RUNNING
    echo "[submit-jobs] === Submitting Bronze Layer ==="
    if ! submit_job "org.rva.BronzeIngestJob" "$USR_LIB/bronze-job.jar" "Bronze"; then
        echo "[submit-jobs] ✗ Bronze job failed, aborting..."
        exit 1
    fi
    echo "[submit-jobs] Bronze job is healthy, proceeding..."
    sleep 5
    
    # Submit Silver job và đợi RUNNING
    echo "[submit-jobs] === Submitting Silver Layer ==="
    if ! submit_job "org.rva.silver.SilverJob" "$USR_LIB/silver-job.jar" "Silver"; then
        echo "[submit-jobs] ✗ Silver job failed, aborting..."
        exit 1
    fi
    echo "[submit-jobs] Silver job is healthy, proceeding..."
    sleep 5
    
    # Submit Gold jobs
    echo "[submit-jobs] === Submitting Gold Layer ==="
    if ! submit_job "org.rva.gold.GoldTrackSummaryJob" "$USR_LIB/gold-jobs.jar" "Gold-TrackSummary"; then
        echo "[submit-jobs] ⚠ Gold-TrackSummary failed, continuing anyway..."
    fi
    
    # Uncomment khi cần thêm Gold jobs khác
    # sleep 3
    # submit_job "org.rva.gold.GoldMinuteByCamJob" "$USR_LIB/gold-jobs.jar" "Gold-MinuteByCam"
    # sleep 3
    # submit_job "org.rva.gold.GoldHourByCamJob" "$USR_LIB/gold-jobs.jar" "Gold-HourByCam"
    
    echo "[submit-jobs] ✓ Job submission complete!"
    echo "[submit-jobs] Check Flink UI at http://localhost:8081 for job status"
}

main "$@"
