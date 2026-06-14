# SUPERSEDED

Tài liệu này phản ánh một hướng triển khai cũ:

- `rva_mart`
- `mart_*`
- `HLL cho unique metrics`
- `cron + Python runner`

Hướng này không còn là kiến trúc chính thức của project.

Nguồn đúng hiện tại:

- [README](../README.md)
- [02_BI_MART_TABLE_DESIGN.md](../02_BI_MART_TABLE_DESIGN.md)
- [03_AIRFLOW_DAGS_AND_OPERATIONS.md](../03_AIRFLOW_DAGS_AND_OPERATIONS.md)
- [06_JOB_MAPPING_AND_DATA_MODELING.md](../06_JOB_MAPPING_AND_DATA_MODELING.md)

Đọc file này chỉ với mục đích lịch sử triển khai và review quyết định cũ.

# Phase 1 — Analyst Mart Layer (HLL, cron, no Airflow)

Ngày thực hiện: `2026-06-12`

## 1. Mục tiêu

Triển khai tầng `rva_mart` để analyst endpoints không còn đọc trực tiếp `silver_*` / `gold_*` cho hot path chính:

- tạo mart schema + DDL
- tạo refresh SQL theo grain của từng mart
- tạo runner refresh và maintenance chạy bằng host cron
- repoint analytics query layer sang mart tables
- verify end-to-end bằng test + refresh thực tế + gọi trực tiếp API layer

Phạm vi phase này bám theo quyết định đã chốt:

- **có mart layer**
- **không Airflow**
- **cron + Python runner**
- **HLL cho unique metrics**

## 2. Files đã thêm / sửa

### 2.1 Mart layer mới

- `services/mart/trino_client.py`
- `services/mart/refresh_runner.py`
- `services/mart/maintenance.py`
- `services/mart/README.md`
- `services/mart/sql/ddl/marts.sql`
- `services/mart/sql/refresh/*.sql`

### 2.2 Query routing + test

- `services/api/src/rva_api/api/v1/analytics_queries.py`
- `tests/unit/test_analytics_queries.py`
- `tests/unit/test_analytics_api.py`

## 3. Mart tables đã tạo

Schema: `lakehouse.rva_mart`

Tables:

- `mart_heatmap_tile_5min`
- `mart_heatmap_tile_hour`
- `mart_traffic_hourly`
- `mart_traffic_daily`
- `mart_queue_hourly`
- `mart_queue_daily`
- `mart_zone_hourly`
- `mart_zone_daily`
- `mart_dwell_daily`
- `mart_executive_daily`
- `mart_alert_hourly`
- `mart_alert_daily`
- `mart_refresh_audit`
- `data_quality_results`

Tất cả DDL đã apply thành công qua `services/mart/trino_client.py`.

## 4. Query routing đã đổi

`services/api/src/rva_api/api/v1/analytics_queries.py` hiện đọc:

- dashboard summary / hourly / camera / daily:
  - `lakehouse.rva_mart.mart_traffic_hourly`
  - `lakehouse.rva_mart.mart_traffic_daily`
  - `lakehouse.rva_mart.mart_dwell_daily`
- queue:
  - `lakehouse.rva_mart.mart_queue_hourly`
  - `lakehouse.rva_mart.mart_queue_daily`
- heatmap:
  - `lakehouse.rva_mart.mart_heatmap_tile_5min` khi `days <= 1`
  - `lakehouse.rva_mart.mart_heatmap_tile_hour` khi `days > 1`
- alerts history:
  - vẫn giữ `lakehouse.rva.gold_alerts`

Ghi chú:

- cache Redis ở `analytics.py` vẫn giữ nguyên
- frontend không cần đổi contract

## 5. Refresh runner và maintenance

### 5.1 Refresh runner

Runner: `services/mart/refresh_runner.py`

Modes:

- `intraday`
- `daily`
- `backfill --start YYYY-MM-DD --end YYYY-MM-DD`

Runner thực hiện:

1. đọc SQL file
2. inject `{start}` / `{end}`
3. chạy `DELETE + INSERT`
4. ghi `mart_refresh_audit`

Đã sửa warning Python:

- thay `datetime.utcnow()` bằng `datetime.now(dt.UTC).replace(tzinfo=None)`

### 5.2 Maintenance

Script: `services/mart/maintenance.py`

Chức năng:

- `OPTIMIZE` cho `silver`, `gold` nóng và các mart chính
- ghi file stats vào `data_quality_results`
- ghi `optimize_failed` nếu gặp conflict thay vì fail cả run

Lý do:

- `gold_queue_sessions` đã từng conflict khi optimize trong lúc Flink/refresh cùng ghi
- maintenance cần degrade gracefully, không được làm hỏng cả pass

## 6. Kết quả verify chính

### 6.1 Unit tests

Lệnh:

```bash
UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/unit/test_analytics_queries.py tests/unit/test_analytics_api.py
UV_CACHE_DIR=/tmp/uvcache uv run ruff check services/api/src/rva_api/api/v1/analytics_queries.py services/mart tests/unit/test_analytics_queries.py tests/unit/test_analytics_api.py
```

Kết quả:

- `10 passed`
- `ruff: All checks passed`

### 6.2 Intraday refresh thực tế

Lệnh:

```bash
cd services/mart
python3 refresh_runner.py intraday
```

Output cuối:

```text
refresh mode=intraday window=[2026-06-12..2026-06-12] run_id=2099bde7edcf
  ok   mart_heatmap_tile_5min       rows=6365
  ok   mart_heatmap_tile_hour       rows=798
  ok   mart_traffic_hourly          rows=3
  ok   mart_traffic_daily           rows=1
  ok   mart_queue_hourly            rows=9
  ok   mart_queue_daily             rows=3
  ok   mart_zone_hourly             rows=9
  ok   mart_zone_daily              rows=3
  ok   mart_dwell_daily             rows=1
  ok   mart_alert_hourly            rows=0
  ok   mart_alert_daily             rows=0
  ok   mart_executive_daily         rows=1
done: 0 failed
```

### 6.3 Audit cuối

`mart_refresh_audit` xác nhận run sạch đã hoàn tất đủ 12 mart, lần lượt:

- `mart_heatmap_tile_5min`
- `mart_heatmap_tile_hour`
- `mart_traffic_hourly`
- `mart_traffic_daily`
- `mart_queue_hourly`
- `mart_queue_daily`
- `mart_zone_hourly`
- `mart_zone_daily`
- `mart_dwell_daily`
- `mart_alert_hourly`
- `mart_alert_daily`
- `mart_executive_daily`

### 6.4 Row counts cuối

```text
mart_heatmap_tile_5min  6365
mart_heatmap_tile_hour   798
mart_traffic_hourly        3
mart_traffic_daily         1
mart_queue_hourly          9
mart_queue_daily           3
mart_zone_hourly           9
mart_zone_daily            3
mart_dwell_daily           1
mart_executive_daily       1
mart_alert_hourly          0
mart_alert_daily           0
```

### 6.5 API layer sau khi đổi routing

Gọi trực tiếp functions:

```text
dashboard ready 3 1 1
queue ready 3 3
heatmap ready 24 32 271
```

Ý nghĩa:

- dashboard data status = `ready`
- queue data status = `ready`
- heatmap data status = `ready`

Mart layer đang phục vụ được analytics path.

## 7. Vấn đề quan trọng phát hiện trong Phase 1

### 7.1 HLL hiện chưa đủ chính xác cho KPI unique

Sau run sạch, đối chiếu:

```text
mart merged_unique = 600
silver exact_unique = 710
```

Sai số khoảng `15.5%`.

Kết luận:

- pipeline HLL **chạy đúng về mặt kỹ thuật**: refresh ok, merge ok, API ok
- nhưng **độ chính xác business hiện chưa đủ đẹp** nếu muốn coi `unique_tracks` là KPI tin cậy

Nguyên nhân thực tế:

- Trino version hiện tại **không support** overload `approx_set(x, e)` trong môi trường này
- đã thử nâng precision lên `0.01`, nhưng engine báo lỗi và chỉ chấp nhận signature mặc định
- vì vậy hiện tại bị khóa ở default precision của engine

### 7.2 Bài học triển khai

Các error giữa chừng trong audit lúc `13:39`–`13:44` là của run thử sai precision HLL, không phải run cuối.

Run cuối `run_id=2099bde7edcf` là run sạch, `done: 0 failed`.

## 8. Đánh giá trạng thái sau Phase 1

### 8.1 Đã xong

- mart schema + DDL
- refresh SQL cho 12 mart
- cron-style runner
- maintenance script
- API query routing sang mart
- tests unit
- refresh thực tế end-to-end

### 8.2 Chưa chốt hẳn

`unique_*` dựa trên HLL hiện **chưa nên coi là final answer** cho dashboard KPI.

Tầng mart hiện phù hợp cho:

- heatmap
- queue
- zone
- dwell
- executive aggregates không phụ thuộc exact unique

Nhưng phần:

- `summary unique_tracks`
- `camera unique_tracks`
- `daily unique_tracks`
- `hourly unique_tracks`

vẫn cần quyết định lại nếu muốn số analyst đủ chặt.

## 9. Khuyến nghị Phase tiếp theo

Ưu tiên kỹ thuật sau Phase 1:

1. **Quyết định lại strategy cho unique metrics**
   - nếu cần exact: đọc từ grain nhỏ hơn / materialize exact counts riêng
   - nếu giữ HLL: phải chấp nhận sai số hoặc nâng cấp engine/version support precision tốt hơn

2. **Tách rõ mart nào được phép dùng HLL**
   - heatmap / queue visitor count có thể chấp nhận approximate
   - KPI headline cho analyst thì nên thận trọng hơn

3. **Giữ maintenance định kỳ**
   - vì mart layer đã chính thức thành serving layer mới

4. **Sau khi chốt unique strategy mới**, mới nên commit phase analyst mart là “ổn hoàn toàn”

## 10. Kết luận ngắn

Phase 1 mart layer đã được **implement xong và chạy end-to-end**.

Điểm còn lại không phải pipeline fail, mà là **độ chính xác của HLL default trên Trino hiện tại không đạt kỳ vọng cho unique KPI**. Đây là issue thiết kế/engine capability, không phải issue wiring hay refresh orchestration.
