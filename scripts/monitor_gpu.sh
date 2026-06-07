#!/usr/bin/env bash
# Thermal/power monitor for diagnosing hard power-off under Vision GPU load.
#
# Logs GPU + CPU telemetry once per second and fsync()s after every line, so the
# LAST line written survives a hard power-off. After the machine reboots, read
# the tail of the CSV to see the GPU temp / power / throttle-reason at the exact
# moment of death — that tells us thermal vs power.
#
# Usage:
#   ./scripts/monitor_gpu.sh            # 1s interval, auto-named log in logs/
#   ./scripts/monitor_gpu.sh 1 logs/run1.csv
set -u

INTERVAL="${1:-1}"
OUT="${2:-logs/thermal_monitor_$(date +%Y%m%d_%H%M%S).csv}"
mkdir -p "$(dirname "$OUT")"

HEADER="ts,gpu_temp_c,gpu_pwr_w,gpu_util_pct,gpu_mem_mib,gpu_clock_mhz,thr_sw_thermal,thr_hw_thermal,thr_power_brake,thr_power_cap,cpu_pkg_c,cpu_max_core_c"
echo "$HEADER" > "$OUT"
sync

echo "Logging to: $OUT   (every ${INTERVAL}s, Ctrl-C to stop)"
echo "$HEADER"

while true; do
  ts=$(date +%H:%M:%S)
  gpu=$(nvidia-smi \
    --query-gpu=temperature.gpu,power.draw,utilization.gpu,memory.used,clocks.sm,clocks_throttle_reasons.sw_thermal_slowdown,clocks_throttle_reasons.hw_thermal_slowdown,clocks_throttle_reasons.hw_power_brake_slowdown,clocks_throttle_reasons.sw_power_cap \
    --format=csv,noheader,nounits 2>/dev/null | sed 's/, /,/g')
  pkg=$(sensors 2>/dev/null | awk -F'[+.]' '/Package id 0:/{print $2; exit}')
  maxcore=$(sensors 2>/dev/null | awk -F'[+.]' '/^Core /{if($2>m)m=$2} END{print m}')
  line="${ts},${gpu},${pkg},${maxcore}"
  echo "$line" | tee -a "$OUT"
  sync   # force the line to disk so it survives a power cut
  sleep "$INTERVAL"
done
