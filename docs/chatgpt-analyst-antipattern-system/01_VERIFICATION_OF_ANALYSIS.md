# Đối chiếu phân tích ChatGPT với code thực tế

Mỗi mục: **claim của ChatGPT → kết quả verify → bằng chứng `file:line` → nhận xét.**
Trạng thái: ✅ Đúng · ⚠️ Đúng một phần / nói quá · ❌ Sai / lỗi thời · ➕ ChatGPT bỏ sót.

---

## A. Nhóm Flink jobs (`system.md`)

### A1. ✅ Checkpoint/savepoint là local
- **Bằng chứng:** `infrastructure/flink/conf/flink-conf.yaml:45-46`
  ```yaml
  state.checkpoints.dir: file:///opt/flink/state/checkpoints
  state.savepoints.dir: file:///opt/flink/state/savepoints
  ```
- **Nhận xét:** Đúng. Trớ trêu là comment ngay trên (`:43`) ghi *"lưu trên S3 thay vì
  Local File"* nhưng config vẫn `file://`. Volume `flink_state` (`docker-compose.yml:303`)
  là named docker volume → state **sống sót qua restart container**, nhưng **mất** khi
  `docker compose down -v` / đổi máy / multi-node. Claim đúng, nhưng nên sửa lại sắc thái:
  không phải "mất ngay khi container chết", mà là "không durable, single-node".

### A2. ✅ Streaming aggregation không có TTL → state vô hạn
- **Bằng chứng:**
  - `GoldTrackSummaryJob.java:89-95` — đọc `silver_detections_v2` streaming, `GROUP BY
    store_id, camera_id, pipeline_run_id, global_track_id`.
  - `QueueAnalyticsJob.java:93-98` — `GROUP BY ... global_track_id`.
  - `GoldDashboardAggregateJob.java:162-167,183-188` — `GROUP BY ... CAST(capture_ts AS DATE)[, HOUR]`.
  - Không có `table.exec.state.ttl` ở bất kỳ job nào (grep toàn repo: không thấy).
- **Nhận xét:** Đúng. Đây là regular streaming aggregation (không phải window), state giữ
  cho mọi key vĩnh viễn.

### A3. ➕ ChatGPT BỎ SÓT: dedup `ROW_NUMBER()` ở Silver cũng unbounded
- **Bằng chứng:** `SilverJob.java:185-189`
  ```sql
  ROW_NUMBER() OVER (
    PARTITION BY COALESCE(b.event_id, ...), COALESCE(t.det_id, CAST(t.track_id AS STRING))
    ORDER BY t.conf DESC, ... DESC) AS rn
  ... WHERE rn = 1
  ```
- **Nhận xét:** Đây là stateful streaming operator giữ state cho **mọi** `(event_id, det_id)`,
  không TTL. Vì `event_id` duy nhất theo từng frame, key space tăng tuyến tính theo *mọi
  detection từng đi qua* → phình **nhanh hơn** các `GROUP BY` Gold mà ChatGPT nêu.
  ChatGPT chỉ soi Gold, không nhắc cái này. **Đây mới là state operator đáng lo nhất.**

### A4. ✅ `parseCaptureMs` fallback về current time — nguy hiểm
- **Bằng chứng:** `ParseDetections.java:215-226`
  ```java
  private static long parseCaptureMs(String ts) {
    if (ts == null) return System.currentTimeMillis();
    ... catch (DateTimeParseException ignore) {}
    return System.currentTimeMillis();   // fallback cuối
  }
  ```
- **Nhận xét:** Đúng và là **correctness bug thật**. `SilverJob.java:195` lọc
  `t.capture_ts_ms IS NOT NULL`, nhưng do fallback nên giá trị **không bao giờ null** →
  record timestamp lỗi bị gán giờ hiện tại → sai `days(capture_ts)` partition, sai daily
  KPI, sai dwell, sai heatmap bucket.

### A5. ✅ Silver không có DLQ (chỉ log + counter)
- **Bằng chứng:** `ParseDetections.java:109-114` — `catch { LOG.warn(...); invalidRecordCounter.inc(); }`.
- **Nhận xét:** Đúng. Realtime path có DLQ Pulsar (`RealtimeMetricsJob.java:104,113...`),
  Silver thì không. Record parse lỗi biến mất, không lưu lại để điều tra.

### A6. ✅ `QueueAnalyticsJob.completed = FALSE` hardcode
- **Bằng chứng:** `QueueAnalyticsJob.java:90` — `"  FALSE AS completed,"`.
- **Nhận xét:** Đúng. Wait time tính bằng `MAX(capture_ts) - MIN(capture_ts)`
  (`:88`) nhưng session lifecycle (enter/exit/close) chưa có; cờ `completed` vô nghĩa.

### A7. ⚠️ Redis sink: không exactly-once / swallow exception / không pipeline
- **Bằng chứng:** `RealtimeMetricsJob.java:448-450` — `catch (Exception e) { LOG.warn(...); }`;
  mỗi event nhiều lệnh Jedis tuần tự (`:406-447`).
- **Nhận xét:** Đúng về sự kiện. Nhưng đánh giá mức độ: với **realtime cache** thì
  best-effort + swallow là **chấp nhận được** (Redis không phải source of truth). Đáng làm
  trong đồ án chỉ là: thêm **metric** `redis_write_failed_total` để không "xanh giả". Pipeline
  Jedis là tối ưu throughput → Future Work.

### A8. ✅ `executeAndAwait` không thật sự await
- **Bằng chứng:** `GoldServingSupport.java:347-349`
  ```java
  static void executeAndAwait(TableEnvironment tEnv, String sql) throws Exception {
      tEnv.executeSql(sql);   // thiếu .await()
  }
  ```
- **Nhận xét:** Đúng. Trong batch mode, `INSERT OVERWRITE` cần `result.await()` để chắc
  chắn job hoàn tất trước khi step sau chạy. Hiện dựa vào REST polling bên ngoài
  (`submit_batch_job.py`) che lấp, nhưng tên method gây hiểu nhầm và là edge case.

### A9. ✅ Audit có code nhưng không ghi
- **Bằng chứng:** `GoldServingBatchJob.java:487-489`
  ```java
  private static void executeStep(TableEnvironment tEnv, Args args, String tableName,
                                  String sourceTable, String sql) throws Exception {
      GoldServingSupport.executeAndAwait(tEnv, sql);   // bỏ qua tableName/sourceTable/audit
  }
  ```
  `GoldServingSupport.writeAudit(...)` (`:368-402`) định nghĩa đầy đủ nhưng **không nơi nào
  gọi** từ batch job.
- **Nhận xét:** Đúng. Bảng `gold_serving_refresh_audit` được tạo nhưng batch job không ghi
  row nào (chỉ Trino python path cũ ghi — xem D1).

### A10. ✅ DDL/catalog lặp trong mọi runtime job
- **Bằng chứng:** Mỗi job lặp lại y hệt block `CREATE CATALOG lakehouse WITH (...)` +
  `getenv/firstNotBlank/ensureWarehouseSuffix`: `BronzeIngestJob.java:21-48`,
  `SilverJob.java:23-45`, `GoldTrackSummaryJob.java:19-47`, `QueueAnalyticsJob.java:24-52`,
  `GoldAlertsJob.java:26-49`, `GoldDashboardAggregateJob.java:26-54`,
  `GoldServingSupport.java:22-50`. `ensureServingTables` (`:53-345`) tạo 14 bảng mỗi lần
  domain chạy.
- **Nhận xét:** Đúng. Code catalog copy-paste 7 lần; nên extract `IcebergCatalogSupport`.

### A11. ✅ SQL viết thành Java string dài
- **Bằng chứng:** Toàn bộ `GoldServingBatchJob.java` (~480 dòng SQL trong `String.join`),
  `SilverJob.java:98-204`.
- **Nhận xét:** Đúng. Khó review/diff/test. Move ra `src/main/resources/sql/*.sql`.

### A12. ✅ Packaging: 1 JAR copy thành nhiều tên
- **Bằng chứng:** `infrastructure/flink/Dockerfile:31-35` — cùng `silver-job-0.1.0.jar`
  copy thành `bronze-job.jar`, `silver-job.jar`, `gold-job.jar`, `gold-jobs.jar`,
  `realtime-job.jar`. Comment `:30` thừa nhận *"cùng một JAR, nhiều tên"*.
- **Nhận xét:** Đúng. "1 JAR nhiều entry class" **không** phải antipattern; nhưng copy
  nhiều tên giả là debt gây hiểu nhầm. Sửa: 1 jar versioned + `--entry-class`.

---

## B. Nhóm Airflow (`system.md`)

### B1. ❌ LỖI THỜI: "SequentialExecutor không chạy song song"
- **Bằng chứng:** `docker-compose.yml:289-290`
  ```yaml
  AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://...@postgres:5432/...
  AIRFLOW__CORE__EXECUTOR: "LocalExecutor"
  ```
- **Nhận xét:** Claim dựa trên trạng thái **trước** migration Postgres. Hiện đã là
  `LocalExecutor` (chạy task song song được). **Lưu ý:** comment trong
  `gold_serving_executive.py:36` vẫn ghi `# ... (required under SequentialExecutor)` →
  bản thân repo còn lệch comment, cần dọn (xem `02_*` P1.7).

### B2. ✅ (bắt rất chuẩn) `executive_daily`: dependency DAG ≠ nguồn SQL thực
- **Bằng chứng:**
  - DAG chờ 4 upstream: `gold_serving_executive.py:11-16` →
    `traffic.refresh_traffic_daily`, `dwell.refresh_dwell`, `queue.refresh_queue_daily`,
    `alert.refresh_alert_daily`.
  - Nhưng `GoldServingBatchJob.runExecutiveDaily` đọc thẳng **raw Gold facts**:
    `rva.gold_track_summary_v2` (`:433`), `rva.gold_queue_sessions` (`:443`),
    `rva.gold_alerts` (`:453`). Chỉ traffic đọc từ serving (`:404,412`
    `rva_gold_serving.gold_serving_traffic_daily/hourly`).
- **Nhận xét:** Đúng — mismatch thật. DAG nói chờ `dwell/queue/alert_daily` nhưng SQL không
  dùng output của chúng (dùng raw facts). Dependency Airflow đang "trang trí".

### B3. ⚠️ Cross-DAG `ExternalTaskSensor` dễ gây nợ vận hành
- **Bằng chứng:** `gold_serving_executive.py:29-41` (4 sensor, `mode="reschedule"`,
  `timeout=3600`).
- **Nhận xét:** Đúng là pattern dễ rối khi catchup+backfill. Nhưng với đồ án 1 store,
  giữ nguyên là **chấp nhận được**; gom master-DAG/TaskGroup là *nên* chứ không *bắt buộc*.
  Xếp P1/Future.

### B4. ✅ Airflow timeout không cancel Flink job → orphan
- **Bằng chứng:** `submit_batch_job.py:114-117` — `finally` chỉ
  `_delete_uploaded_jar(...)`, **không** call cancel `/jobs/{id}` endpoint.
- **Nhận xét:** Đúng. Nếu task fail/timeout, Flink batch job có thể tiếp tục chạy ngầm.

### B5. ✅ REST submit thiếu cancel / job_id tracking / artifact versioning
- **Bằng chứng:** `submit_batch_job.py` upload→run→poll→delete; job_id chỉ `print`
  (`:112`), không push XCom; jar path mặc định cố định `:18`.
- **Nhận xét:** Đúng. Dùng được cho local/non-K8s; production-hardening → Future Work.

---

## C. Nhóm Partition (`partition-strateric.md`)

### C1. ✅ Bronze chỉ `PARTITIONED BY (store_id)`, không có cột ngày
- **Bằng chứng:** `BronzeIngestJob.java:50-61` (`PARTITIONED BY (store_id)`), cột thời gian
  duy nhất là `ingest_ts` = `CURRENT_TIMESTAMP` (`:86`). Không có `capture_ts`/`business_date`.
- **Nhận xét:** Đúng về fact.

### C2. ⚠️ "Bronze là antipattern lớn nhất" — NÓI QUÁ
- **Lý do:** Trong kiến trúc hiện tại Bronze **không bị query theo date range**. `SilverJob`
  đọc Bronze bằng streaming incremental (`SilverJob.java:190`:
  `OPTIONS('streaming'='true','starting-strategy'='TABLE_SCAN_THEN_INCREMENTAL')`), không
  phải batch theo ngày. Use case "replay/debug theo ngày" là *giả định*, chưa phải query
  path thật. ⇒ Debt **tiềm ẩn**, không "lớn nhất".

### C3. ✅ Silver `store_id,bucket(16,camera_id),days(capture_ts)`
- **Bằng chứng:** `SilverJob.java:93`.
- **Nhận xét:** Đúng. ChatGPT đánh giá "khá ổn" — hợp lý.

### C4. ⚠️ Lo ngại pruning `days(capture_ts)` vs `CAST(... AS DATE)`
- **Nhận xét:** Hơi quá. Trino Iceberg connector prune tốt trên transform `days()` khi
  filter bằng predicate ngày (transform pushdown). Vấn đề **thật** không phải `days()`, mà
  là **timezone**: `capture_ts` là `TIMESTAMP_LTZ` (UTC); hệ thống **chưa có `business_date`
  theo local timezone của store** ⇒ "Today/Yesterday" trên UI tính theo UTC, lệch ngày với
  store ở Sydney. Đây là điểm đúng và đáng ghi nhận.

### C5. ✅ Serving tables thiếu `store_id` trong partition
- **Bằng chứng:** `GoldServingSupport.java` — toàn bộ serving table dùng
  `'partitioning' = 'metric_date,bucket(16, camera_id)'` (vd `:72,93,111,153...`);
  `executive_daily` chỉ `'metric_date'` (`:262`). `store_id` chỉ là cột thường.
- **Nhận xét:** Đúng. UI filter business đầu tiên là Store ⇒ thiếu `store_id` partition là
  lệch query pattern. Với demo 1 store thì vô hại, nhưng đúng về hướng.

### C6. ✅ `gold_alerts` partition `days(event_ts)` dù có store_id/event_date
- **Bằng chứng:** `GoldAlertsJob.java:51-72` — cột `store_id,camera_id,event_date,event_ts`
  nhưng `'partitioning' = 'days(event_ts)'` (`:70`).
- **Nhận xét:** Đúng.

### C7. ⚠️ Anti-pattern "partition không gắn Airflow `{{ ds }}`" — nói quá
- **Lý do:** Serving tables **đã** partition theo `metric_date`, và SQL batch derive
  `metric_date` từ `--start/--end = {{ ds }}` (`common.py:20-24`). Tức **đã** khớp. Gap thật
  chỉ là thiếu chiều `store_id` + chưa chuẩn hóa `business_date`.

---

## D. Nhóm trùng lặp Gold serving (`system.md` #6)

### D1. ✅ Tồn tại 2 implementation: Trino python + Flink batch
- **Bằng chứng:**
  - Flink batch (đang dùng cho refresh): tất cả `gold_serving_*` DAG gọi `submit_batch_cmd`
    → `submit_batch_job.py` → `GoldServingBatchJob.java`.
  - Trino python (path cũ): `services/gold_serving/refresh_runner.py` + `sql/refresh/*.sql`
    vẫn còn; nhưng **chỉ** `gold_quality_checks` và `iceberg_maintenance` còn gọi python
    runner (`quality_checks.py`, `maintenance.py`) qua `bash_in_runner` (`common.py:16`).
- **Nhận xét:** Đúng. Hiện trạng **hybrid**: refresh đã migrate sang Flink batch,
  DQ/maintenance còn ở Trino python. `refresh_runner.py` + `sql/refresh/*.sql` thực tế đã
  **chết** cho refresh theo lịch ⇒ source-of-truth nhập nhằng, logic metric dễ lệch 2 nơi.

---

## Tổng kết verify

| Hạng mục | Số claim | ✅ Đúng | ⚠️ Đúng một phần | ❌ Sai/lỗi thời |
|---|---:|---:|---:|---:|
| Flink jobs | 12 | 10 | 2 | 0 |
| Airflow | 5 | 3 | 1 | 1 |
| Partition | 7 | 4 | 3 | 0 |
| Gold serving dup | 1 | 1 | 0 | 0 |

➕ ChatGPT **bỏ sót**: unbounded state của dedup Silver (A3) — đáng ra phải là điểm state
ưu tiên số 1.

**Kết luận:** Phân tích của ChatGPT đáng tin cậy ở mức cao, nhưng cần đính chính B1
(SequentialExecutor lỗi thời), giảm nhẹ C2/C4/C7 (partition nói quá), và bổ sung A3.
Lộ trình sửa ở `02_REMEDIATION_PLAN.md`.
