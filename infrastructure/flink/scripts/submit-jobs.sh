#!/bin/bash
# Automatically submit Flink jobs after JobManager is ready.

set -euo pipefail

FLINK_HOME=${FLINK_HOME:-/opt/flink}
USR_LIB=${FLINK_USR_LIB_DIR:-/opt/flink/usrlib}

wait_for_jobmanager() {
  echo "[submit-jobs] Waiting for JobManager..."
  local max_attempts=60
  local attempt=0

  while [ "${attempt}" -lt "${max_attempts}" ]; do
    if curl -sf http://flink-jobmanager:8081/overview > /dev/null 2>&1; then
      echo "[submit-jobs] JobManager is ready."
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 2
  done

  echo "[submit-jobs] ERROR: JobManager did not become ready after ${max_attempts} attempts."
  return 1
}

check_job_status_by_id() {
  local job_id=$1
  local max_wait=60
  local attempt=0

  echo "[submit-jobs] Waiting for job ${job_id} to become RUNNING..."

  while [ "${attempt}" -lt "${max_wait}" ]; do
    local response
    response=$(curl -sf "http://flink-jobmanager:8081/jobs/${job_id}" 2>/dev/null || true)

    if [ -n "${response}" ]; then
      if echo "${response}" | grep -q '"state":"RUNNING"'; then
        echo "[submit-jobs] Job ${job_id} is RUNNING."
        return 0
      fi
      if echo "${response}" | grep -q '"state":"FAILED"'; then
        echo "[submit-jobs] ERROR: Job ${job_id} is FAILED."
        return 1
      fi
      if echo "${response}" | grep -q '"state":"CANCELED"'; then
        echo "[submit-jobs] ERROR: Job ${job_id} is CANCELED."
        return 1
      fi
      if echo "${response}" | grep -q '"state":"FINISHED"'; then
        echo "[submit-jobs] ERROR: Job ${job_id} finished unexpectedly."
        return 1
      fi
    fi

    attempt=$((attempt + 1))
    sleep 2
  done

  echo "[submit-jobs] ERROR: Timeout waiting for job ${job_id} to be RUNNING."
  return 1
}

get_running_job_ids() {
  curl -sf "http://flink-jobmanager:8081/jobs/overview" 2>/dev/null \
    | grep -oE '"jid":"[0-9a-f]+"' | grep -oE '[0-9a-f]{32}' | sort || true
}

submit_job() {
  local class_name=$1
  local jar_file=$2
  local job_name=$3
  local max_retries=3
  local retry=0

  while [ "${retry}" -lt "${max_retries}" ]; do
    echo "[submit-jobs] Submitting ${job_name}..."

    # Snapshot existing IDs so we can detect a newly created job even if
    # the flink-run client is killed by timeout before printing the JobID.
    local before_ids
    before_ids=$(get_running_job_ids)

    local out=""
    if ! out=$(timeout 120s "${FLINK_HOME}/bin/flink" run -d -c "${class_name}" "${jar_file}" 2>&1); then
      out=""
    fi

    local job_id=""
    job_id=$(echo "${out}" | grep -Eo 'JobID [0-9a-f]+' | awk '{print $2}' | tail -n 1 || true)

    # Client timed-out or printed no JobID — diff before/after to find the new job.
    if [ -z "${job_id}" ]; then
      sleep 3
      local after_ids
      after_ids=$(get_running_job_ids)
      job_id=$(comm -13 <(echo "${before_ids}") <(echo "${after_ids}") | head -1 || true)
      if [ -n "${job_id}" ]; then
        echo "[submit-jobs] ${job_name} found in Flink via API with JobID ${job_id}."
      fi
    fi

    if [ -z "${job_id}" ]; then
      echo "[submit-jobs] ERROR: Could not determine JobID for ${job_name}."
      retry=$((retry + 1))
      echo "[submit-jobs] Retry ${retry}/${max_retries} for ${job_name}..."
      sleep 5
      continue
    fi

    echo "[submit-jobs] ${job_name} submitted with JobID ${job_id}."
    if check_job_status_by_id "${job_id}"; then
      return 0
    fi

    retry=$((retry + 1))
    echo "[submit-jobs] Retry ${retry}/${max_retries} for ${job_name}..."
    sleep 5
  done

  echo "[submit-jobs] ERROR: Failed to submit ${job_name} after ${max_retries} attempts."
  return 1
}

main() {
  wait_for_jobmanager || exit 1

  echo "[submit-jobs] Waiting for TaskManager registration..."
  sleep 10

  echo "[submit-jobs] === Submitting Bronze Layer ==="
  if ! submit_job "org.rva.BronzeIngestJob" "${USR_LIB}/bronze-job.jar" "Bronze"; then
    echo "[submit-jobs] ERROR: Bronze job failed, aborting."
    exit 1
  fi

  echo "[submit-jobs] === Submitting Silver Layer ==="
  if ! submit_job "org.rva.silver.SilverJob" "${USR_LIB}/silver-job.jar" "Silver"; then
    echo "[submit-jobs] ERROR: Silver job failed, aborting."
    exit 1
  fi

  echo "[submit-jobs] === Submitting Gold Layer ==="
  if ! submit_job "org.rva.gold.GoldTrackSummaryJob" "${USR_LIB}/gold-jobs.jar" "Gold-TrackSummary"; then
    echo "[submit-jobs] WARN: Gold-TrackSummary failed, continuing anyway."
  fi

  echo "[submit-jobs] === Submitting Queue Analytics Gold Layer ==="
  if ! submit_job "org.rva.gold.QueueAnalyticsJob" "${USR_LIB}/gold-jobs.jar" "Gold-QueueAnalytics"; then
    echo "[submit-jobs] WARN: Gold-QueueAnalytics failed, continuing anyway."
  fi

  echo "[submit-jobs] === Submitting RealtimeMetrics Job ==="
  if ! submit_job "org.rva.realtime.RealtimeMetricsJob" "${USR_LIB}/realtime-job.jar" "RealtimeMetrics"; then
    echo "[submit-jobs] WARN: RealtimeMetrics failed, continuing anyway."
  fi

  echo "[submit-jobs] === Submitting Gold Alerts Job ==="
  if ! submit_job "org.rva.gold.GoldAlertsJob" "${USR_LIB}/gold-jobs.jar" "GoldAlertsJob"; then
    echo "[submit-jobs] WARN: GoldAlertsJob failed, continuing anyway."
  fi

  echo "[submit-jobs] === Submitting Gold Dashboard Aggregate Job ==="
  if ! submit_job "org.rva.gold.GoldDashboardAggregateJob" "${USR_LIB}/gold-jobs.jar" "Gold-DashboardAggregate"; then
    echo "[submit-jobs] WARN: Gold-DashboardAggregate failed, continuing anyway."
  fi

  echo "[submit-jobs] Job submission complete."
  echo "[submit-jobs] Check Flink UI at http://localhost:8081 for job status"
}

main "$@"
