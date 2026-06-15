# 07 — Fact Table Partition Analysis (Step 3)

> **Scope:** Phân tích vấn đề "fact tables unpartitioned" — bước #3 trong danh sách next-steps sau khi Phase 1–5 đã commit (`75398c9`).
> **Trạng thái:** ANALYSIS ONLY. Chưa lập plan, chưa implement. Plan + implement sẽ làm ở bước sau theo yêu cầu.
> **Ngày:** 2026-06-14
> **Liên quan:** `03_PARTITION_REDESIGN.md` (decision gốc), `06_PROGRESS_2026-06-14.md` §8 (root cause Flink bỏ qua `partitioning`), memory `flink-ignores-partitioning-property`.

---

## 1. Vấn đề (problem statement)

Ba bảng **fact** lõi của pipeline được khai báo partition trong code Flink, nhưng **runtime lại unpartitioned**:

| Table | Khai báo trong DDL (Flink) | Cơ chế dùng | Kết quả runtime |
|---|---|---|---|
| `rva.silver_detections_v2` | `'partitioning' = 'store_id,bucket(16, camera_id),days(capture_ts)'` | WITH property | **UNPARTITIONED** |
| `rva.gold_track_summary_v2` | `'partitioning' = 'store_id,bucket(16, camera_id),days(visit_date)'` | WITH property | **UNPARTITIONED** |
| `rva.gold_alerts` | `'partitioning' = 'days(event_ts)'` | WITH property | **UNPARTITIONED** (hiện 0 rows) |

Nguyên nhân gốc đã được xác định ở §8 của `06_PROGRESS`: **Flink Iceberg connector bỏ qua hoàn toàn (silent no-op) table property `'partitioning'`**. Chỉ có hai cơ chế thực sự tạo partition:
- **Flink `PARTITIONED BY (...)`** — chỉ chấp nhận cột **identity**; parser Flink 1.18 **từ chối** transform (`bucket(...)`, `days(...)`).
- **Trino DDL `partitioning = ARRAY[...]`** — chấp nhận cả transform (`day(...)`, `bucket(...)`).

Đối chứng: `bronze_raw` dùng `PARTITIONED BY (store_id)` (identity) → **CÓ** partition ở runtime. Các serving table đã được sửa ở Phase 5 → CÓ partition. Chỉ còn 3 fact table này vẫn dùng cơ chế cũ bị bỏ qua.

---

## 2. Bằng chứng runtime (đã verify hôm nay, qua Trino)

### 2.1 `$partitions` metadata — phép thử quyết định
Iceberg chỉ expose cột `partition` trong bảng `$partitions` khi bảng **thực sự** partitioned.

```
bronze_raw            $partitions cols: ['partition', 'record_count', 'file_count', 'total_size', 'data']  ✅ partitioned (store_id)
silver_detections_v2  $partitions cols: ['record_count', 'file_count', 'total_size', 'data']               ❌ KHÔNG partitioned
gold_track_summary_v2 $partitions cols: ['record_count', 'file_count', 'total_size', 'data']               ❌ KHÔNG partitioned
gold_alerts           (0 rows; DDL dùng 'partitioning' bị bỏ qua → sẽ unpartitioned khi có data)
```

### 2.2 Quy mô dữ liệu hiện tại (để ước lượng rủi ro migration)

| Table | Rows | Files | Size | Nguồn tái tạo |
|---|---|---|---|---|
| `bronze_raw` | 331,972 | 296 | 105.9 MB | Pulsar `persistent://retail/metadata/events` (`earliest`) |
| `silver_detections_v2` | 1,763,331 | 175 | 78.7 MB | `bronze_raw` (Iceberg streaming scan) |
| `gold_track_summary_v2` | 1,548 | 175 | 18.7 MB | `silver_detections_v2` (Iceberg streaming scan) |
| `silver_detection_parse_errors` | 0 | — | — | — |
| `gold_alerts` | 0 | — | — | Pulsar `media-events` (`earliest`) |

> Quy mô còn nhỏ (đồ án) → migration rẻ. Nhưng đây chính là lý do cần làm **bây giờ**: rewrite 1.7M rows rẻ hơn nhiều so với khi production scale.

---

## 3. Vì sao nó quan trọng (impact analysis)

### 3.1 Read pattern của batch serving jobs (Flink batch)
Các job serving (`GoldServingBatchJob` → resource SQL) đọc fact table với predicate theo NGÀY:

| Serving SQL | Đọc từ | Predicate lọc |
|---|---|---|
| `traffic_hourly/daily`, `heatmap_5min/hour`, `zone_hourly/daily` | `silver_detections_v2` | `CAST(capture_ts AS DATE) BETWEEN d1 AND d2` + `class_id = 0` |
| `dwell_daily` | `gold_track_summary_v2` | `visit_date BETWEEN d1 AND d2` |
| `queue_hourly/daily` | (qua silver/queue view) | `wait_time_sec >= 0` |

→ Mọi refresh "hôm nay" hiện đang **full-scan toàn bộ 1.76M rows** rồi mới lọc 1 ngày. Với partition theo ngày, mỗi refresh chỉ chạm partition của ngày đó (Iceberg partition pruning ở Flink source).

### 3.2 Tác động cụ thể
- **Refresh cost tăng tuyến tính theo lịch sử**: càng nhiều ngày dữ liệu, mỗi lần refresh "today" càng chậm dù chỉ cần 1 ngày. Đây là anti-pattern chính ChatGPT nêu — và nó **đúng**.
- **Buffer/parallelism pressure**: full-scan input lớn hơn → shuffle nặng hơn trên cluster 1-TaskManager đã chật (xem regression buffer ở §6 của `06_PROGRESS`).
- **Không có data skipping cho query ad-hoc** trên fact table (vd debug, reprocess 1 ngày).
- **`gold_alerts`**: hiện 0 rows nên impact = 0 *bây giờ*, nhưng sẽ unpartitioned ngay khi có alert. Rủi ro thấp, fix rẻ → nên gộp luôn.

### 3.3 Mức độ ưu tiên nội bộ bước #3
- `gold_alerts`: **rủi ro thấp, lợi ích vận hành** (đang rỗng → migrate gần như free). Ứng viên làm trước.
- `silver_detections_v2`: **lợi ích cao nhất** (bảng to nhất, bị scan nhiều nhất) nhưng **rủi ro cao nhất** (streaming writer đang chạy, là nguồn của gold).
- `gold_track_summary_v2`: lợi ích trung bình, rủi ro trung bình (upsert + PK, nguồn của dwell).

---

## 4. Read predicate vs partition transform — điểm thiết kế then chốt

Predicate đọc là `CAST(capture_ts AS DATE) BETWEEN ...`. Để partition pruning hoạt động, layout partition phải **khớp** transform của predicate. Có 2 hướng:

### Hướng A — Trino DDL với transform `day(capture_ts)`
- Tạo bảng bằng **Trino**: `partitioning = ARRAY['store_id', 'day(capture_ts)']` (bucket camera_id tùy chọn).
- Flink streaming sink **ghi theo partition spec đọc từ catalog** (không tự tạo spec, nhưng tôn trọng spec sẵn có của bảng đã load). → Cần **verify** Flink writer honor được transform spec do Trino tạo (serving table trước đó dùng identity, chưa chứng minh với transform).
- Ưu: giữ nguyên schema, partition "đẹp" theo ngày, pruning chuẩn với predicate hiện tại.
- Nhược: phụ thuộc hành vi Flink-writes-into-Trino-spec với transform (RỦI RO cần POC).

### Hướng B — Thêm cột identity `capture_date DATE` (materialized) + `PARTITIONED BY` Flink
- Thêm cột `capture_date = CAST(capture_ts AS DATE)` (và tương tự `visit_date` đã sẵn có cho gold_track).
- Partition identity: `PARTITIONED BY (store_id, capture_date)` — Flink-native, không transform, **chắc chắn chạy**.
- Sửa serving SQL: lọc thẳng `capture_date BETWEEN ...` thay vì `CAST(capture_ts AS DATE)`.
- Ưu: cơ chế đã được chứng minh (giống bronze/serving Phase 5), không phụ thuộc hành vi chưa chắc chắn.
- Nhược: thêm 1 cột; phải sửa serving SQL + writer SQL (silver job INSERT phải tính `capture_date`).

> **Gộp `business_date` / timezone (bước #3 trong next-steps gốc):** nếu chọn Hướng B, đây là thời điểm rẻ nhất để thêm luôn cột `business_date` (ngày theo giờ địa phương `Asia/Ho_Chi_Minh`) và **partition theo `business_date` thay vì `capture_date` UTC**. Tránh recreate bảng 2 lần. `gold_track_summary_v2` đã có `visit_date` (đang là `CAST(MIN(capture_ts) AS DATE)` UTC) — cần quyết định có chuyển sang local-time không.

`gold_track_summary_v2` đã có sẵn cột `visit_date` (DATE, identity-friendly) → Hướng B đặc biệt rẻ ở đây: chỉ cần `PARTITIONED BY (store_id, visit_date)`.

---

## 5. Ràng buộc & rủi ro migration

Iceberg **partition evolution** chỉ áp dụng cho dữ liệu GHI MỚI; dữ liệu cũ giữ layout cũ. Muốn bảng partitioned "sạch" cho toàn bộ lịch sử → phải **rewrite dữ liệu hiện có**. Vì các bảng này đều tái tạo được, hướng khả thi là **recreate + reprocess**, không phải ALTER tại chỗ.

### 5.1 Ràng buộc
1. **Streaming writer đang chạy liên tục** vào `silver_detections_v2` (từ bronze) và `gold_track_summary_v2` (từ silver, upsert). Recreate bảng phải **stop job → drop/recreate → restart job**.
2. **Phụ thuộc chuỗi**: `bronze_raw` → silver → gold_track → serving. Nguồn gốc `bronze_raw` (331K rows, đã partitioned, durable) là điểm replay an toàn. Pulsar source dùng `earliest` → có thể replay từ đầu nếu cần.
3. **`starting-strategy = TABLE_SCAN_THEN_INCREMENTAL`**: khi restart job đọc bảng nguồn, nó scan toàn bộ bảng nguồn rồi mới incremental → reprocess full lịch sử là khả thi nhưng tốn 1 lượt full-scan.
4. **`gold_track_summary_v2` dùng `write.upsert.enabled=true` + PK** → recreate phải giữ nguyên upsert semantics; partition cột phải nằm trong/khớp với khóa để tránh ghi sai.
5. **Trino DDL vs Flink DDL phải ĐỒNG BỘ partition spec** (bài học Phase 5: nếu lệch spec → race khi cả hai cùng `CREATE IF NOT EXISTS`). Nguồn chân lý partition cho fact table cần chốt rõ.
6. **Checkpoint/offset Pulsar**: nếu chỉ recreate Iceberg table mà không reset subscription, writer có thể tiếp tục từ offset hiện tại → **mất dữ liệu lịch sử** trong bảng mới. Cần kế hoạch: hoặc reset subscription về `earliest`, hoặc backfill bảng mới từ bronze trước khi bật lại streaming.

### 5.2 Rủi ro
| Rủi ro | Mức | Ghi chú |
|---|---|---|
| Flink writer không honor Trino transform spec (Hướng A) | Cao | Phải POC trước khi cam kết |
| Mất dữ liệu lịch sử khi recreate (offset/subscription) | Cao | Cần backfill-from-bronze hoặc reset earliest |
| Lệch spec Trino/Flink gây race CREATE | Trung bình | Đã gặp ở Phase 5; có quy trình xử lý |
| Downtime streaming trong lúc recreate | Trung bình | Đồ án chấp nhận được; production cần blue/green |
| Buffer exhaustion khi reprocess full-scan parallelism>1 | Trung bình | Giữ `parallelism.default=1` như Phase 5 |
| Sửa serving SQL (Hướng B) làm hỏng refresh | Thấp | Có test path qua DAG today_refresh |

---

## 6. Câu hỏi mở cho bước lập plan (chưa quyết ở đây)

1. **Chọn Hướng A (Trino transform) hay Hướng B (cột identity)?** — khuyến nghị sơ bộ: **Hướng B** vì cơ chế đã chứng minh, không phụ thuộc hành vi chưa chắc; nhưng cần xác nhận chấp nhận thêm cột + sửa serving SQL.
2. **Có gộp `business_date`/timezone (local-time) vào đợt này không?** — nếu có, recreate 1 lần; partition theo `business_date` local thay vì UTC.
3. **Partition key cho `silver_detections_v2`**: `(store_id, <date>)` là đủ, hay cần thêm `bucket(camera_id)`? — với quy mô đồ án + 1 store, `bucket(camera_id)` có thể thừa (over-partitioning → small files). Khuyến nghị sơ bộ: **bỏ bucket camera_id**, chỉ `(store_id, date)`.
4. **Chiến lược dữ liệu lịch sử**: backfill bảng mới từ `bronze_raw` trước khi bật streaming, hay reset Pulsar subscription `earliest` và để pipeline tự dựng lại? — ảnh hưởng downtime & tính toàn vẹn.
5. **Thứ tự triển khai**: `gold_alerts` (rỗng, an toàn) trước để rốt-đa quy trình, rồi `gold_track_summary_v2`, cuối cùng `silver_detections_v2` (rủi ro cao nhất)?
6. **Nguồn chân lý partition spec** cho fact table: chốt Flink DDL hay Trino DDL là "owner" để tránh race.

---

## 7. Tóm tắt (executive summary)

- **Đã xác nhận bằng runtime**: `silver_detections_v2`, `gold_track_summary_v2`, `gold_alerts` đều **unpartitioned** (không có cột `partition` trong `$partitions`), do Flink bỏ qua `'partitioning'` WITH. `bronze_raw` partitioned đúng (dùng `PARTITIONED BY`).
- **Impact thật**: mọi refresh serving full-scan fact table thay vì prune theo ngày → chậm dần theo lịch sử, tăng áp lực shuffle/buffer. Đây là anti-pattern đúng đắn cần sửa, và sửa **bây giờ** rẻ (1.76M rows).
- **Hai hướng kỹ thuật**: (A) Trino DDL transform `day(...)` — cần POC writer honor; (B) cột identity `capture_date`/`visit_date` + `PARTITIONED BY` — đã chứng minh, khuyến nghị sơ bộ.
- **Ràng buộc lớn nhất**: streaming writer đang chạy + nguy cơ mất lịch sử khi recreate → cần kế hoạch backfill/replay rõ ràng (bronze là nguồn an toàn, Pulsar `earliest`).
- **Cơ hội gộp**: thêm `business_date` local-time trong cùng đợt recreate để khỏi làm 2 lần.
- **Trạng thái**: phân tích xong. **Chờ yêu cầu lập plan** → sẽ chốt 6 câu hỏi mở ở §6 rồi mới implement.

---

## 8. Implementation log (2026-06-14) — Option B, code đã áp

**Quyết định đã chốt:** Option B (cột identity `*_date` + Flink `PARTITIONED BY`), timezone **UTC** (`capture_date = CAST(capture_ts AS DATE)`, KHÔNG làm `business_date` local-tz — defer), partition key `(store_id, <date>)` **bỏ `bucket(camera_id)`** (1 store, dữ liệu nhỏ), scope = **7 bảng** (3 fact lõi + 4 bảng dashboard).

### Code changes đã thực hiện
| File | Thay đổi |
|---|---|
| `SilverJob.java` | + cột `capture_date DATE`; `PARTITIONED BY (store_id, capture_date)`; thêm `capture_date` vào INSERT (outer + inner SELECT, derive `CAST(TO_TIMESTAMP_LTZ(t.capture_ts_ms,3) AS DATE)`) |
| `GoldTrackSummaryJob.java` | `PARTITIONED BY (store_id, visit_date)` (cột sẵn có) |
| `GoldAlertsJob.java` | `PARTITIONED BY (store_id, event_date)` (cột sẵn có) |
| `GoldDashboardAggregateJob.java` | 4 DDL: hourly/daily_metrics/daily_dwell → `PARTITIONED BY (store_id, metric_date)`; alert_events → `(store_id, event_date)` |
| serving SQL active (`resources/.../{traffic_hourly,zone_hourly,zone_daily,heatmap_5min,alert_hourly}.sql`) | predicate `CAST(...) BETWEEN` → `capture_date`/`event_date BETWEEN` |
| serving SQL legacy (`gold_serving/sql/refresh/{traffic_hourly,zone_hourly,zone_daily,heatmap_5min,alert_hourly,executive_daily}.sql`) | predicate swap như trên |
| `quality_checks.py:125` | `CAST(capture_ts AS date) = current_date` → `capture_date = current_date` |

Verify code: `grep` predicate-cast còn lại = rỗng; cả 7 DDL có `PARTITIONED BY`, không còn `'partitioning'` WITH (trừ `silver_detection_parse_errors` — out-of-scope, không có cột date identity).

### Operator runbook (user tự chạy)
- **P0 build:** rebuild Flink image (Dockerfile → fat jar).
- **P1 gold_alerts (trước, rủi ro thấp):** cancel GoldAlertsJob → Trino `DROP TABLE IF EXISTS lakehouse.rva.gold_alerts;` → resubmit → Airflow `gold_serving_alert` rồi `gold_serving_executive`.
- **P2 silver chain:** cancel Dashboard→Realtime→Queue→TrackSummary→Silver (giữ Bronze). Trino drop: `gold_track_summary_v2`, `gold_camera_hourly_metrics`, `gold_camera_daily_metrics`, `gold_camera_daily_dwell`, `gold_alert_events`, `silver_detections_v2`. Resubmit `submit-jobs.sh`; chờ silver rebuild từ `bronze_raw` (~1.76M rows).
- **P3 serving backfill:** Airflow `gold_serving_{traffic,zone,heatmap,dwell,queue,alert}` rồi `gold_serving_executive`; chạy `gold_quality_checks`.

### Verify sau rebuild
- `SELECT * FROM lakehouse.rva."<table>$partitions"` → có struct `partition`.
- `EXPLAIN ... WHERE capture_date = DATE '...'` → partition filter / ít splits.
- No-dup trên bảng upsert; serving + API trả data; quality checks không `error`.

### Follow-up (chưa làm)
- `silver_detection_parse_errors`: vẫn dính `'partitioning'='days(processing_ts)'` bị bỏ qua (low-volume DLQ, không có cột date identity) — partition nếu cần ở đợt khác.
- `business_date` local-tz: defer.

---

## 9. Hoàn thành (2026-06-15) — VERIFIED ✅

**Trạng thái phase: HOÀN THÀNH phần lõi.** Cả 7 fact table đã partition thật ở runtime, jobs RUNNING, facts populate.

### Kết quả verify (qua Trino, sau rebuild + restart)
| Tiêu chí | Kết quả |
|---|---|
| `partitioning` runtime (SHOW CREATE / $partitions) | ✅ cả 7: silver→`[store_id,capture_date]`, track→`[store_id,visit_date]`, alerts/alert_events→`[store_id,event_date]`, 3 camera_*→`[store_id,metric_date]` |
| Partition pruning (`EXPLAIN ... WHERE capture_date=...`) | ✅ `TableScan ... constraint on [capture_date]` |
| No-dup trên bảng upsert | ✅ hourly/daily_metrics/track_summary = 0 nhóm trùng |
| Facts có data | ✅ silver 430K, track 1.9K, camera_* đầy; gold_alerts/alert_events=0 (đúng — event-driven) |

### 2 phát hiện phát sinh khi implement (không có trong plan gốc)
1. **UPSERT mode bắt buộc partition col nằm trong equality fields (PRIMARY KEY).** Khi bật `write.upsert.enabled=true`, mọi partition field phải thuộc PK, nếu không Flink fail: *"In UPSERT mode, partition field 'X' should be included in equality fields"*. → đã thêm partition col vào PK của `gold_track_summary_v2` (+visit_date), `gold_alerts` (+store_id,event_date), `gold_alert_events` (+store_id,event_date). Vì `CREATE TABLE IF NOT EXISTS` là no-op, các bảng tạo bằng jar cũ phải **DROP rồi để jar mới tạo lại** (data dev = 0 rows, bỏ được).
2. **Iceberg infer-source-parallelism** (riêng biệt với adaptive batch scheduler) suy parallelism=split-count (cap 100) → batch serving scan của `gold_queue_sessions` (nhiều file nhỏ do streaming commit) bị p=100 trên cluster 16 slot → `gold_serving_queue` job FAILED. Fix: `table.exec.iceberg.infer-source-parallelism: false` trong `flink-conf.yaml`. Chi tiết + backlog tối ưu DAG: xem `08_SERVING_DAG_LATENCY_2026-06-15.md`.

### Còn lại (operational, không thuộc lõi phase)
- Full serving backfill 6 domain + `executive` + `gold_quality_checks` (đang verify domain `queue_hourly` sau fix parallelism) — đây là track latency của doc `08`, không phải vấn đề partition.
- API smoke test (traffic/heatmap/alerts/queue) trả 200 + có data.
- Follow-up §8 (parse_errors partition, business_date local-tz) vẫn defer.
