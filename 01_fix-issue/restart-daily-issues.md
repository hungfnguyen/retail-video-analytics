# Issue: Các vấn đề phát sinh khi restart hệ thống hàng ngày

**Ngày phát hiện:** 2026-06-24  
**Bối cảnh:** Hệ thống không chạy liên tục — mỗi ngày stop rồi start lại  
**Status:** Đã phân tích, chưa fix

---

## 1. Bối cảnh

Project chạy trên AWS EC2 (Singapore) và Vision service chạy local. Do giới hạn chi phí và tài nguyên, hệ thống **không chạy 24/7** — mỗi ngày khởi động thủ công và tắt sau khi demo/test xong.

Thiết kế ban đầu của một số thành phần giả định hệ thống chạy liên tục, dẫn đến một số issue khi restart thường xuyên.

---

## 2. Issues

### Issue 1 — Analytics charts trống tối đa 30 phút sau restart (CRITICAL)

**Triệu chứng:** Sau khi `docker compose up`, mọi chart trên Analytics dashboard (traffic, dwell, queue, zone) hiện data của ngày hôm qua hoặc trống hoàn toàn trong khoảng 30 phút.

**Root cause:**

DAG `gold_serving_today_refresh` schedule `*/30 * * * *` với `catchup=False`:

```
Stack restart lúc 9:00
  → First DAG run: 9:30 (hoặc 10:00 nếu vừa lỡ 30-min slot)
  → Trong window đó: gold_serving tables KHÔNG có data hôm nay
  → Analytics API query → trả về 0 hoặc data ngày cũ
```

**File liên quan:**
- `infrastructure/airflow/dags/gold_serving_today_refresh.py` — schedule `*/30 * * * *`, catchup=False
- `services/gold_serving/sql/refresh/` — SQL refresh cho từng domain

---

### Issue 2 — Live dashboard ~90 giây dead time sau restart (MEDIUM)

**Triệu chứng:** Ngay sau khi stack start, Live Monitor hiện occupancy = 0, heatmap trống, không có track nào.

**Root cause:**

`flink-job-submitter` phải chờ tuần tự:

```
docker compose up
  → flink-jobmanager healthy         (~30s)
  → sleep 10s (TaskManager register)
  → submit Bronze → wait RUNNING
  → submit SilverRealtimeJob → wait RUNNING
  → submit Gold jobs...
  ≈ 90 giây tổng cộng trước khi data chảy vào Redis
```

Trong 90s này:
- `stats:count:{cam}` không tồn tại → API trả về 0 người
- `heatmap:live:{cam}` trống → Heatmap page empty
- Alert evaluator phát hiện pipeline lag → bắn alert giả

**File liên quan:**
- `infrastructure/flink/scripts/submit-jobs.sh` — sequential job submission
- `services/flink-jobs/java/src/main/java/org/rva/realtime/RealtimeMetricsJob.java` — writes Redis live keys

---

### Issue 3 — GoldTrackSummaryJob mất state → dwell analytics sai (MEDIUM)

**Triệu chứng:** `duration_sec` của các track bị ngắt giữa chừng bởi restart bằng 0 hoặc rất nhỏ. Tỉ lệ `short dwell` tăng bất thường sau mỗi ngày restart.

**Root cause:**

`GoldTrackSummaryJob` là streaming aggregation job, **không có Flink savepoint**:

```
Người vào store lúc 9:05, hệ thống stop lúc 9:10
  → Job state bị xóa (flink_state volume chứa checkpoint nhưng không restore)
  → Restart hôm sau: track đó không còn trong Flink state
  → duration_sec không được ghi, track bị drop khỏi gold_track_summary_v2

Kết quả: dwell_band bị lệch về "short" (<30s) dù thực tế người đứng lâu hơn
```

**File liên quan:**
- `services/flink-jobs/java/src/main/java/org/rva/gold/GoldTrackSummaryJob.java`
- `infrastructure/flink/scripts/submit-jobs.sh` — submit không dùng `-s <savepoint>`

---

### Issue 4 — Alert history mất sau mỗi restart (LOW)

**Triệu chứng:** Sau restart, tab Alerts trên Live Monitor trống hoàn toàn dù hôm qua có alerts.

**Root cause:**

Redis không có persistent volume → mọi alert key bị xóa khi restart:

```yaml
# docker-compose.yml — không có redis_data volume
volumes:
  trino_data: ✅
  flink_state: ✅
  pulsar_data: ✅
  pg_data: ✅
  # redis_data: ← KHÔNG CÓ
```

Alert evaluator repopulate sau ~10s nhưng **chỉ tạo alert mới** khi có threshold violation mới — không restore lịch sử. Alert lịch sử dài hạn chỉ tồn tại trong `gold_alerts` (Iceberg), không hiện trực tiếp trên Live Monitor.

**File liên quan:**
- `services/api/src/rva_api/alert_evaluator.py` — viết vào `alert:live:{cam}` ZSET (24h TTL)
- `docker-compose.yml` — Redis service không có volume mount

---

### Issue 5 — SilverRealtimeJob xử lý Pulsar backlog chậm (INFO)

**Triệu chứng:** Trong ~5–10 phút đầu sau restart, Silver và Gold tables nhận data chậm hơn bình thường dù Vision đã chạy.

**Root cause:**

`SilverRealtimeJob` dùng named subscription `flink-silver-realtime-ok` — Pulsar nhớ offset. Sau restart, job phải process toàn bộ messages chưa ack từ lần stop trước trước khi xử lý realtime:

```
Stop lúc 11:00 PM, restart lúc 9:00 AM hôm sau
  → 10h backlog trong Pulsar (pulsar_data volume còn giữ)
  → Silver job process backlog trước
  → Gold serving data đổ vào chậm hơn ~5-10 phút
```

Đây là hành vi **đúng về correctness** (không mất data), nhưng gây delay initial analytics.

**File liên quan:**
- `services/flink-jobs/java/src/main/java/org/rva/silver/SilverRealtimeJob.java` — subscription `flink-silver-realtime-ok`

---

## 3. Timeline thực tế sau mỗi restart

```
T+0s    docker compose up
T+30s   Flink JobManager healthy, Redis/Pulsar/Trino ready
T+90s   Tất cả Flink jobs RUNNING → pipeline hoạt động
T+10m   Vision service khởi động thủ công → live frame/count có data
T+30m*  gold_serving_today_refresh chạy lần đầu → analytics charts có data hôm nay
T+24h   @daily DAGs (dwell/queue/zone) chạy → data ngày hôm qua hoàn chỉnh

* worst case: restart đúng lúc vừa lỡ 30-min slot → phải chờ đến slot tiếp theo
```

---

## 4. Những thứ KHÔNG bị ảnh hưởng khi restart

| Thành phần | Lý do an toàn |
|---|---|
| Iceberg tables (bronze/silver/gold) | Lưu trên S3, không mất |
| Gold Serving schema (`rva_gold_serving`) | Iceberg catalog dùng Postgres JDBC — persist qua restart |
| Airflow DAG history và state | Postgres-backed (`pg_data` volume) |
| Pulsar messages | `pulsar_data` volume — persist, Silver job sẽ process backlog |
| Analytics Redis cache bị xóa | **Tốt** — buộc fresh Trino query thay vì serve stale data |

---

## 5. Hướng xử lí (chưa implement)

| Issue | Hướng fix | Độ phức tạp |
|---|---|---|
| Analytics trống 30 phút | Trigger `gold_serving_today_refresh` ngay khi stack start (startup script hoặc Airflow sensor) | Thấp |
| Live dead time 90s | Chấp nhận cho demo — hoặc pre-warm Redis với last known values trước khi Flink ready | Trung bình |
| Dwell sai do restart | Bật Flink savepoint/checkpoint recovery cho GoldTrackSummaryJob | Cao |
| Alert history mất | Thêm `redis_data` volume + Redis persistence (`appendonly yes`) | Thấp |
| Pulsar backlog delay | Thêm lag metric monitoring — không cần fix, chỉ cần document | Không cần fix |
