# Airflow Orchestration

Thư mục này chứa skeleton orchestration cho kiến trúc:

- `Bronze / Silver / Gold`
- `Flink` là transform engine chính
- `Airflow` chỉ là orchestrator cho batch refresh và maintenance

## DAG hiện có

- `dags/gold_serving_intraday_refresh.py`
  - task `apply_gold_serving_ddl` (bootstrap schema idempotent) → `refresh_runner.py intraday --skip-ddl`
  - mục tiêu: đảm bảo schema tồn tại rồi refresh các bảng Gold serving trong ngày

- `dags/gold_serving_daily_finalize.py`
  - task `apply_gold_serving_ddl` → `refresh_runner.py daily --skip-ddl`
  - mục tiêu: đảm bảo schema tồn tại rồi finalize serving partition của ngày hôm qua

> Task `apply_gold_serving_ddl` (chạy `apply_ddl.py`) dựng lại `rva_gold_serving` sau mỗi restart.
> Vì DDL idempotent, refresh dùng `--skip-ddl` để tránh chạy 2 lần trong cùng DAG run.

- `dags/iceberg_maintenance.py`
  - chạy `services/gold_serving/maintenance.py`
  - mục tiêu: `OPTIMIZE` + lightweight DQ checks

## Thiết kế

Airflow không chứa logic transform.

Nó chỉ gọi các script orchestration có sẵn bằng `BashOperator`.
Điều này giữ cho:

- SQL/Trino logic vẫn nằm trong `services/gold_serving/`
- Airflow chỉ chịu trách nhiệm schedule, retry, dependency
- sau này nếu thay `Trino SQL` bằng `Flink batch`, DAG chỉ cần đổi command target

## Environment variables

Các DAG dùng các biến sau:

- `RVA_PROJECT_ROOT`
  - mặc định: `/opt/retail-video-analytics`
- `RVA_PYTHON_BIN`
  - mặc định: `/usr/bin/python3`
- `RVA_SERVING_RUNNER_DIR`
  - mặc định: `${RVA_PROJECT_ROOT}/services/gold_serving`

## Ghi chú

`services/gold_serving/` hiện là implementation vật lý của **Gold serving**.
