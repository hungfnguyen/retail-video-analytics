# Roadmap Triển Khai Airflow Analyst Layer

Tài liệu này chia lộ trình thêm Airflow vào project theo phase. Mục tiêu là cải thiện tầng analyst mà không làm vỡ pipeline Vision/Flink/Redis hiện tại.

## 1. Mục tiêu cuối

Kiến trúc mong muốn:

```text
Vision -> Pulsar -> Flink Realtime -> Redis -> Live UI
Vision -> Pulsar -> Flink Lakehouse -> Bronze/Silver/Gold Iceberg
Gold/Silver -> Airflow -> Mart Iceberg tables
Mart tables -> Trino -> FastAPI cache -> Analyst UI
```

Mục tiêu kỹ thuật:

- dashboard analyst không query Silver mặc định;
- historical heatmap đọc mart aggregate;
- mart refresh có audit;
- Iceberg có maintenance định kỳ;
- API analytics có cache;
- UI có status rõ ràng cho cold-start/stale/empty.

## 2. Phase 0 - Baseline và đo hiệu năng hiện tại

Mục tiêu:

```text
Biết dashboard chậm ở đâu trước khi thay đổi.
```

Tasks:

1. **Verify nền Gold trước tiên** (prerequisite): stack chạy lại → `SHOW TABLES IN lakehouse.rva` + `COUNT(*)` cho cả 4 bảng dashboard (`gold_camera_hourly_metrics`, `gold_camera_daily_metrics`, `gold_camera_daily_dwell`, `gold_alert_events`). Xác nhận submit-fix (commit `600be79`) đã giải quyết job-not-running. **Nếu daily vẫn rỗng dù hourly có data → debug `GoldDashboardAggregateJob` trước khi xây bất kỳ mart nào** (mart traffic/dwell source từ chính các bảng này).
2. Ghi lại query hiện tại của từng endpoint analytics.
3. Đo response time P50/P95 cho:
   - dashboard overview;
   - queue analytics;
   - heatmap 1d/7d/14d;
   - alert history.
4. Kiểm tra Iceberg file count/snapshot count:
   - `silver_detections_v2$files` (kỳ vọng phát hiện small files: ~2.500 file / ~96K rows);
   - `gold_queue_sessions$files`;
   - `gold_zone_minute_metrics$files`.
5. **Compaction + đo lại (quyết định phạm vi mart):** chạy `OPTIMIZE` trên `silver_detections_v2` (recent partitions) rồi **đo lại heatmap latency**. Nếu đã đủ nhanh ở scale hiện tại → **hạ ưu tiên `mart_heatmap_*`** (small files mới là nút thắt, không phải row volume — xem `01 §1`).
6. **Sửa non-additive ngay trong `analytics_queries.py` hiện tại:** `summary_sql` đang `SUM(daily.unique_tracks)` qua nhiều ngày → đếm trùng (xem `02 §1.5`).
7. Kiểm tra endpoint nào query Silver.

Acceptance:

```text
4 bảng Gold dashboard tồn tại và có data (hoặc đã có ticket fix nếu rỗng).
Có bảng baseline latency TRƯỚC và SAU compaction.
Có quyết định: mart heatmap còn cần thiết hay không ở scale hiện tại.
Có danh sách endpoint cần chuyển sang mart.
```

## 3. Phase 1 - Thiết kế và tạo mart schema

Mục tiêu:

```text
Tạo namespace mart và các bảng ưu tiên.
```

Tables ưu tiên:

```text
lakehouse.rva_mart.mart_heatmap_tile_5min
lakehouse.rva_mart.mart_heatmap_tile_hour
lakehouse.rva_mart.mart_traffic_hourly
lakehouse.rva_mart.mart_queue_hourly
lakehouse.rva_mart.mart_zone_hourly
lakehouse.rva_mart.mart_refresh_audit
lakehouse.rva_mart.data_quality_results
```

Tasks:

1. Thêm SQL DDL cho `rva_mart` schema.
2. Thêm DDL cho mart tables.
3. Tạo scripts local để chạy DDL qua Trino.
4. Document grain của từng table.

Acceptance:

```text
SHOW TABLES FROM lakehouse.rva_mart trả về mart tables.
Schema có partition hợp lý.
```

## 4. Phase 2 - Historical heatmap mart

Mục tiêu:

```text
Giải quyết pain point lớn nhất: heatmap không scan Silver mỗi request.
```

Tasks:

1. Tạo SQL refresh `mart_heatmap_tile_5min` từ `silver_detections_v2`.
2. Tạo SQL rollup `mart_heatmap_tile_hour` từ `mart_heatmap_tile_5min`.
3. Thêm audit row sau refresh.
4. Sửa FastAPI heatmap endpoint query mart trước.
5. Giữ fallback Silver cho debug hoặc khi mart chưa có data.
6. Thêm cache cho heatmap endpoint.

Acceptance:

```text
Heatmap 1d/7d đọc mart table.
Response time heatmap giảm rõ rệt.
UI hiển thị source=mart_heatmap_tile_hour hoặc source=mart_heatmap_tile_5min.
```

## 5. Phase 3 - Airflow local deployment

Mục tiêu:

```text
Đưa Airflow vào docker-compose hoặc compose profile riêng.
```

Components:

```text
airflow-webserver
airflow-scheduler
airflow-worker optional
postgres metadata db
```

Dev choice:

```text
LocalExecutor đủ cho demo/dev.
CeleryExecutor chưa cần nếu workload nhỏ.
```

> **Ràng buộc RAM (host 15GB) — bắt buộc:** full stack + 3 camera đã chạm 11–12GB và từng freeze. Airflow (webserver + scheduler + Postgres) tốn thêm ~1–2GB.
> - Đưa Airflow vào **compose profile riêng** (`docker compose --profile airflow up`), **không** bật cùng lúc live demo 3 camera.
> - Chỉ `LocalExecutor` + Postgres nhẹ; tắt example DAGs (`AIRFLOW__CORE__LOAD_EXAMPLES=False`); giảm `parsing_processes`.
> - Phương án nhẹ cho thesis: nếu chỉ cần mart-refresh + maintenance, có thể dùng **cron + script Trino** thay Airflow. Chọn Airflow khi muốn trình diễn orchestration trong luận văn.

Tasks:

1. Thêm `services/airflow/`.
2. Thêm Dockerfile hoặc dùng image Airflow official.
3. Thêm requirements/provider:
   - Trino provider hoặc Python client;
   - Redis client optional.
4. Mount DAGs và SQL files.
5. Thêm `.env` variables cho Trino/Iceberg/Redis.

Acceptance:

```text
Airflow UI mở được.
DAGs parse thành công.
Manual trigger test DAG chạy được query Trino đơn giản.
```

## 6. Phase 4 - Intraday mart refresh DAG

Mục tiêu:

```text
Tự động refresh mart trong ngày.
```

DAG:

```text
analytics_mart_intraday_refresh
```

Tasks:

1. `check_trino_available`
2. `check_source_freshness`
3. `refresh_mart_heatmap_tile_5min`
4. `refresh_mart_heatmap_tile_hour`
5. `refresh_mart_traffic_hourly`
6. `refresh_mart_queue_hourly`
7. `refresh_mart_zone_hourly`
8. `run_light_quality_checks`
9. `warm_api_cache`
10. `write_refresh_audit`

Schedule:

```text
*/15 * * * *
```

> **Refresh window — chỉ last 1–2 giờ, không cả ngày:** `DELETE current-day + INSERT` mỗi 15 phút trên Iceberg v2 sinh delete-files + data-files mỗi lần chạy → chính mart tích tụ small files/delete files (96 lần/ngày). Mặc định nên refresh **last 1–2h** (hoặc partition mart theo giờ và overwrite partition giờ hiện tại). Để maintenance DAG (Phase 6) compact mart định kỳ.

Acceptance:

```text
DAG chạy định kỳ.
Mart row count tăng/cập nhật.
Audit table ghi status.
API heatmap/dashboard dùng cache sau DAG.
Cột unique_* được recompute/HLL, KHÔNG SUM khi rollup (xem 02 §1.5).
```

## 7. Phase 5 - Daily finalize DAG

Mục tiêu:

```text
Chốt dữ liệu ngày hôm qua theo kiểu warehouse.
```

DAG:

```text
analytics_mart_daily_finalize
```

Tables:

```text
mart_traffic_daily
mart_queue_daily
mart_zone_daily
mart_dwell_daily
mart_alert_daily
mart_executive_daily
```

Schedule:

```text
0 2 * * *
```

Acceptance:

```text
Ngày hôm qua có mart daily đầy đủ.
Dashboard daily không cần scan Gold/Silver.
```

## 8. Phase 6 - Iceberg maintenance DAG

Mục tiêu:

```text
Giảm small files, metadata growth và improve Trino planning.
```

DAG:

```text
iceberg_table_maintenance
```

Tasks:

1. inspect file/snapshot metrics;
2. optimize mart recent partitions;
3. optimize hot Gold tables;
4. optimize Silver recent partitions nếu cần;
5. optimize manifests;
6. expire snapshots với retention an toàn;
7. remove orphan files với retention an toàn;
8. ANALYZE mart tables.

Acceptance:

```text
avg_file_size tăng.
file_count giảm.
Trino query P95 giảm.
Không làm Flink jobs fail.
```

## 9. Phase 7 - Data quality và observability

Mục tiêu:

```text
Biết mart nào stale/sai trước khi UI bị ảnh hưởng.
```

Tasks:

1. Thêm `data_quality_results`.
2. Check source freshness.
3. Check duplicate keys theo mart grain.
4. Check row count anomaly.
5. Check non-negative metrics.
6. Expose status trong System page hoặc API.

Acceptance:

```text
System/analytics status biết mart đang ready/stale/failed.
UI không còn blank khi mart chưa sẵn sàng.
```

## 10. Phase 8 - Query routing cleanup

Mục tiêu:

```text
Đảm bảo analyst UI không query Silver mặc định.
```

Tasks:

1. Review `analytics_queries.py`.
2. Chuyển heatmap sang mart.
3. Chuyển traffic/queue/zone sang mart nếu có.
4. Giữ fallback Silver có flag/debug only.
5. Thêm response metadata:
   - `source_table`;
   - `data_status`;
   - `latest_refresh_ts`;
   - `cached`.

Acceptance:

```text
Default dashboard path chỉ đọc mart/Gold.
Silver query chỉ còn ở debug/drill-down.
```

## 11. Phase 9 - Backfill workflow

Mục tiêu:

```text
Có khả năng rebuild mart khi đổi logic.
```

DAG:

```text
analyst_backfill
```

Parameters:

```text
start_date
end_date
mart_names
camera_ids
force_refresh
```

Acceptance:

```text
Backfill 1 ngày hoặc nhiều ngày thành công.
Audit ghi rõ run_id và output row count.
```

## 12. Rủi ro và cách giảm

| Rủi ro | Cách giảm |
|---|---|
| Airflow làm phức tạp stack | Bắt đầu với LocalExecutor và ít DAG |
| Mart refresh ghi quá nhiều | Refresh current day trước, tối ưu incremental sau |
| Cleanup Iceberg làm ảnh hưởng Flink | Retention rộng, không cleanup aggressive |
| Duplicate mart keys | DQ check theo grain |
| UI vẫn chậm | Cache + query mart + inspect Trino explain |
| Trino single-node nghẽn | Cache, mart nhỏ, sau đó mới scale Trino |

## 13. Ưu tiên thực tế cho project hiện tại

Thứ tự mình khuyên làm:

1. Tạo `mart_heatmap_tile_5min/hour`.
2. Sửa Heatmap API query mart + cache.
3. Thêm Airflow local với `analytics_mart_intraday_refresh`.
4. Thêm audit tables.
5. Thêm maintenance DAG cho mart tables.
6. Mở rộng traffic/queue/zone marts.
7. Thêm daily finalize.
8. Thêm data quality và System status.

Lý do:

```text
Heatmap là nơi có lợi ích performance rõ nhất.
Airflow có thể chứng minh giá trị ngay qua mart refresh + cache.
Các dashboard khác có thể migrate dần mà không phá pipeline live.
```

## 14. Definition of Done

Tầng Airflow analyst được xem là ổn khi:

- Airflow UI hiển thị DAGs chạy định kỳ.
- `rva_mart` có tables và audit.
- Heatmap không còn query `silver_detections_v2` mặc định.
- Analytics endpoints trả `source_table`, `data_status`, `cached`.
- Trino query dashboard P95 giảm rõ rệt.
- Iceberg maintenance không làm Flink jobs fail.
- Có tài liệu runbook để restart/debug Airflow DAGs.
