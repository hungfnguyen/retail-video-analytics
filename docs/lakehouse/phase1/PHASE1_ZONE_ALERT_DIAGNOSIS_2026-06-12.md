# Phase 1 — Diagnosis: gold_zone_minute_metrics = 0 & gold_alerts/gold_alert_events = 0

Người thực hiện: Claude (Opus 4.8)
Ngày: 2026-06-12
Phạm vi: điều tra root cause 2 "feature đang chết" theo roadmap (mục 1 & 2). **Kết quả: cả hai premise đều lệch — không phải bug feature người dùng thấy, mà là 1 bug Flink trên bảng mồ côi + 1 bảng rỗng đúng-thiết-kế.**

---

## Tóm tắt

| Bảng | Trạng thái | Root cause (verified) | Có ai dùng? |
|---|---|---|---|
| `gold_zone_minute_metrics` | 0 rows, **0 snapshots** | Flink insert plan thành **bounded**, finished mà không commit | ❌ **Mồ côi** — không endpoint nào query |
| `gold_alerts` | 0 rows | Clip chỉ trigger khi **>10 người/frame**; thực tế max = **8** → không clip nào fire | ✅ Alert History UI đọc bảng này |
| `gold_alert_events` | 0 rows | Tương tự density threshold (GoldDashboardAggregateJob) | ❌ Mồ côi |

---

## 1. gold_zone_minute_metrics — bug Flink thật, nhưng bảng mồ côi

### 1.1. Bằng chứng

- Nguồn CÓ data: `silver_detections_v2` có 14,685/29,686 rows với `primary_zone_id` (3 zone).
- Logic SQL ĐÚNG: chạy batch trong Trino cho **13,257 rows**.
- Nhưng bảng: **0 snapshots, 0 files, 0 records** → chưa từng commit.
- Flink job graph (`QueueAnalyticsJob`, cùng 1 StatementSet):
  - Nhánh `gold_queue_sessions`: source `monitor` = **RUNNING**, committer RUNNING → 72 sessions ✓
  - Nhánh `gold_zone_minute_metrics`: source + GroupAggregate×2 + **Join** + GroupAggregate + SinkMaterializer = **FINISHED**; writer out=1 file, committer in=1 nhưng **0 snapshot**.

### 1.2. Root cause

Insert zone dùng pattern `GROUP BY → regular stream-stream JOIN → GROUP BY` feeding upsert sink (cần `SinkMaterializer`). Flink plan nhánh này thành **bounded** (source scan 1 lần rồi FINISHED), thay vì streaming monitor như nhánh queue. Trong cùng 1 job với nhánh streaming không bao giờ kết thúc:

- nhánh bounded ghi 1 file vào IcebergFilesCommitter,
- nhưng commit chỉ xảy ra khi checkpoint complete,
- task đã FINISHED + job tổng vẫn RUNNING → file pending **mồ côi, không bao giờ thành snapshot**.

→ Thủ phạm là **stream-stream JOIN + nested retract aggregation**, không phải logic nghiệp vụ.

### 1.3. Bảng này KHÔNG có ai dùng

`grep` toàn API: queue/zone dashboard đọc `gold_queue_sessions` (queue_zone_summary_sql, queue_wait_trend_sql), KHÔNG đọc `gold_zone_minute_metrics`. Vậy 0 rows của nó **không làm hỏng feature nào**.

### 1.4. Fix đề xuất (nếu giữ bảng)

Rewrite zone insert thành **single-level streaming GROUP BY** (giống pattern queue_sessions đang chạy ổn), bỏ stream-stream JOIN:

```sql
INSERT INTO rva.gold_zone_minute_metrics
SELECT store_id, camera_id, primary_zone_id AS zone_id,
  COALESCE(primary_zone_type,'unknown') AS zone_type,
  FLOOR(capture_ts TO MINUTE) AS window_start,
  FLOOR(capture_ts TO MINUTE) + INTERVAL '1' MINUTE AS window_end,
  CAST(COUNT(*) AS DOUBLE) / NULLIF(COUNT(DISTINCT frame_index), 0) AS avg_occupancy,
  COUNT(DISTINCT global_track_id) AS unique_visitors,
  COUNT(*) AS detection_count
FROM rva.silver_detections_v2 /*+ OPTIONS(streaming, monitor-interval, TABLE_SCAN_THEN_INCREMENTAL) */
WHERE primary_zone_id IS NOT NULL AND global_track_id IS NOT NULL AND capture_ts IS NOT NULL
GROUP BY store_id, camera_id, primary_zone_id, primary_zone_type, FLOOR(capture_ts TO MINUTE)
```

Đánh đổi: bỏ `max_occupancy` (peak per-frame) vì nó cần 2 level — single-level không tính được; `avg_occupancy` định nghĩa lại = người/frame trung bình (count / distinct frames). Cần **rebuild gold-jobs.jar + cancel/resubmit QueueAnalyticsJob** (động vào pipeline streaming đang chạy).

---

## 2. gold_alerts — KHÔNG phải bug, rỗng đúng thiết kế

### 2.1. Bằng chứng

- Topic `persistent://retail/metadata/media-events`: **msgInCounter = 0** (chưa từng có message).
- `GoldAlertsJob` khỏe: subscription `flink-gold-alerts-sub`, 1 consumer, backlog 0 → đói input, không lỗi.
- Config ĐÃ bật: `cameras.yaml` `media_upload_enabled: true`, `alert_clip_enabled: true`.
- Clip trigger (`worker.py:487`): chỉ khi `len(detections) > alert_density_threshold` (default **10**) → `alert_type=density_high`.
- Thực tế người/frame (2 ngày, cam_01): **max = 8**, avg = 3.9, p95 = 7.

→ Ngưỡng 10 **không bao giờ đạt** (max chỉ 8) → không clip nào fire → topic rỗng → `gold_alerts = 0`.

### 2.2. Lưu ý nguồn alert khác nhau

Alert `long_wait` đang nằm trong Redis (`alert:item:cam_01_..._long_wait_*`, UI live thấy 5 cái) do **API alert_evaluator** (queue wait time) sinh. Chúng **không** đi vào pipeline clip→media-events→gold_alerts. Hai nguồn alert tách biệt; Alert History (gold_alerts) chỉ phản ánh **density-clip incidents**, không phản ánh queue alerts.

### 2.3. Fix đề xuất

- **Lựa chọn rẻ nhất:** hạ `alert_density_threshold` 10 → **6** trong `cameras.yaml` (p95=7 nên sẽ fire thi thoảng). Cần **restart vision worker**; clip extraction (ffmpeg transcode + S3 upload) chạy trên máy GPU. ⚠️ Lưu ý lịch sử Xid 120 GSP crash — đây là tải thêm trên GPU box.
- Hoặc chấp nhận rỗng (đúng thiết kế) + cho UI hiện empty-state "no incidents" rõ ràng.
- `gold_alert_events` (mồ côi) cùng nguyên nhân density; không ai query → không cần đụng.

---

## 3. Kết luận thẳng (no over-engineering)

- **Item 1**: bug Flink thật nhưng trên **bảng không ai dùng**. "Fix" nó (rebuild + redeploy streaming job) chỉ đáng làm nếu sẽ wire zone-occupancy thành feature thật; nếu không → **xóa insert mồ côi** là lựa chọn lean nhất.
- **Item 2**: **không có gì để "fix" về code** — pipeline đúng, chỉ là ngưỡng density không đạt trong demo. Muốn Alert History có data thì hạ ngưỡng (config, + restart worker, + chi phí GPU) hoặc chấp nhận rỗng.

Cả hai mutation đều **động vào pipeline streaming / vision worker trên máy GPU nhạy cảm** → cần quyết định của bạn trước khi thực thi (xem 2 câu hỏi kèm theo).

---

## 4. Trạng thái thực thi (đã làm — 2026-06-12)

Quyết định người dùng: **Item 1 = xóa orphan**, **Item 2 = hạ ngưỡng density 10→6**.

### Item 1 — gold_zone_minute_metrics: XÓA orphan ✅

1. Xóa `createZoneMinuteMetrics` + `insertZoneMinuteMetrics` khỏi `QueueAnalyticsJob.java` (giữ comment giải thích). Job giờ chỉ ghi `gold_queue_sessions`.
2. `mvn clean package -DskipTests` → build OK (`silver-job-0.1.0.jar`).
3. Hot-swap jar vào `flink-jobmanager` + `flink-taskmanager` (`gold-jobs.jar`, `gold-job.jar`).
4. Cancel job cũ (REST `PATCH /jobs/{jid}?mode=cancel`) → resubmit `QueueAnalyticsJob` (JobID `ad17afc2...`).
5. **Verify**: job mới RUNNING, tên chỉ còn `insert-into_lakehouse.rva.gold_queue_sessions`; `gold_queue_sessions` vẫn có data (262 rows, đang tăng).
6. `DROP TABLE lakehouse.rva.gold_zone_minute_metrics` (rỗng, không consumer) → đã xóa.

⚠️ Lưu ý deploy: jar được swap nóng vào container đang chạy. Lần build lại Docker image tiếp theo sẽ tự cuốn theo source đã sửa (Dockerfile `mvn package`), nên không cần thao tác thủ công lại.

### Item 2 — gold_alerts: hạ ngưỡng density ✅ (cần 1 bước restart thủ công)

1. `configs/cameras.yaml`: `alert_density_threshold: 10 → 6` (kèm comment lý do). Trigger `>6` sẽ fire ở frame có ≥7 người (p95=7, max=8) → tần suất thưa, có `alert_cooldown_sec: 60` chống spam.
2. ⏳ **Cần bạn restart vision worker** để nạp config mới — đây là host process trong tmux `rva:vision` (không tự kill vì máy GPU nhạy cảm). Sau restart, khi có ≥7 người/frame → `density_high` clip → topic `media-events` → `GoldAlertsJob` ghi `gold_alerts` → Alert History UI có data.
3. Chưa verify end-to-end được cho tới khi worker restart + có frame đông người.

### Không đụng tới

- `gold_alert_events` (mồ côi, cùng nguyên nhân density) — để nguyên.
- Pipeline alert API-side (`long_wait` trong Redis) — ngoài phạm vi 2 item này.
