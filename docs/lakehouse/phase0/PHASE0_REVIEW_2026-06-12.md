# Phase 0 Review & Verification — Lakehouse Analyst Layer

Người đánh giá: Claude (Opus 4.8)
Ngày: 2026-06-12
Đối tượng: `PHASE0_BASELINE_2026-06-12.md` (do Codex tạo) + code thực tế Codex sửa.
Phương pháp: đọc diff code, chạy lại test, đo lại runtime độc lập trên stack đang chạy.

---

## TL;DR

| Hạng mục | Kết luận |
|---|---|
| Fix correctness `unique_tracks` | ✅ **Đúng, đã verify.** Đây là giá trị thật của Phase 0. |
| Test + lint | ✅ Verify lại: `5 passed`. |
| Trạng thái stack (7 jobs RUNNING) | ✅ Khớp baseline. |
| OPTIMIZE giảm file count | ✅ Đúng (18→1, 20→1). |
| **Headline: "compaction → dashboard 4.3s"** | ❌ **KHÔNG tái lập được.** Tôi đo 12→19s **kể cả sau khi re-OPTIMIZE về 1 file**; Codex đo lại độc lập **26–30s** (data lớn hơn nữa). |
| **Decision 1: "compaction là đủ, chưa cần mart"** | ⚠️ **Không được dữ liệu ủng hộ.** Vấn đề latency dashboard là thật và đang xấu đi theo data volume. |

Tóm gọn: phần **correctness** của Codex chắc và nên giữ. Phần **kết luận về performance** dựa trên một con số đo đúng *tại một thời điểm* nhưng không bền và không tái lập — không nên dùng làm căn cứ quyết định kiến trúc. Codex đã cross-check lại review này và **xác nhận hướng** (đảo ưu tiên Phase 1: cache trước), đồng thời **bắt một lỗi chi tiết của tôi** ("4 query tuần tự" → thực ra song song) — đã đính chính ở §2.3.

---

## 1. Verify phần correctness (PASS)

Đã đọc diff `services/api/src/rva_api/api/v1/analytics_queries.py`:

- `summary_sql`: thêm CTE `tracks` đếm `COUNT(DISTINCT CONCAT(camera_id, ':', pipeline_run_id, ':', track_id))` từ `silver_detections`, `CROSS JOIN` + `MAX()` để lấy scalar. Bỏ `SUM(daily.unique_tracks)`.
- `hourly_sql` / `camera_sql` / `daily_sql`: thêm CTE `track_counts` group theo hour / camera / date, `LEFT JOIN` vào gold aggregate. Bỏ hết `SUM(unique_tracks)`.

Đánh giá pattern: **đúng**. Track identity gồm `pipeline_run_id` nên không đụng track_id giữa các run; recompute từ base grain là cách chuẩn để fix non-additive. Các cột additive (`detections`, `avg_conf` weighted) vẫn lấy từ gold — hợp lý.

Verify chạy thật:

```text
uv run pytest tests/unit/test_analytics_queries.py  -> 5 passed (0.05s)
```

Test mới `test_dashboard_unique_tracks_are_recomputed_from_base_grain` assert đúng trọng tâm (có recompute từ silver, không còn `SUM(unique_tracks)`).

Sanity-check số liệu baseline: `total_detections = 39,728` = đúng rowcount `silver_detections` tại thời điểm đó; `unique_tracks = 96` = khớp `gold_track_summary`. Tự nhất quán → fix đáng tin.

---

## 2. Verify phần performance (FAIL TÁI LẬP)

Đây là điểm tôi không đồng ý với baseline. Baseline §7 báo: sau compaction dashboard ~4.3s (từ ~12s).

### 2.1. Compaction không bền — streaming phân mảnh lại trong vài giờ

| Bảng | Codex sau OPTIMIZE | Tôi đo lại (cùng ngày, vài giờ sau) |
|---|---:|---:|
| `silver_detections` | 1–2 files | **18 files** |
| `silver_detections_v2` | 1 file | **20 files** |
| `gold_camera_hourly_metrics` | 2 files | **17 files** |
| `gold_camera_daily_metrics` | 2 files | **17 files** |

Flink commit mỗi ~30s checkpoint → mỗi checkpoint đẻ file mới. OPTIMIZE một lần là vô nghĩa nếu không có job định kỳ.

### 2.2. Nhưng file count KHÔNG phải nguyên nhân chính

Tôi chạy lại `OPTIMIZE` đưa `silver_detections` và `_v2` **về đúng 1 file**, rồi đo lại dashboard:

```text
dashboard?days=7  sau khi đã compaction về 1 file:
  15.7s / 16.9s / 16.9s   ... rồi  18.8s / 19.2s
```

→ File về 1 mà latency **vẫn 16–19s, còn tệ hơn lúc 18 file (12s)**. Vậy compaction **không phải đòn bẩy** cho endpoint dashboard.

### 2.3. Nguyên nhân thật: data volume tăng + exact distinct nặng + Trino single-node

> **Đính chính (Codex bắt đúng, 2026-06-12):** Bản đầu tôi viết dashboard bắn "4 query tuần tự" — **sai**. Code thật `services/api/src/rva_api/api/v1/analytics.py:101` dùng `ThreadPoolExecutor(max_workers=4)` + `as_completed`, tức 4 query (summary/hourly/camera/daily) chạy **song song**. Đính chính này làm kết luận **mạnh thêm**, không yếu đi: xem dưới.

- `silver_detections`: **39,728 → 74,367 → 87,115 rows** (Codex đo lại sau tôi); `silver_detections_v2`: → 79,900 → 88,626. Dataset chạy live, latency leo theo: tôi đo 12→16→19s, Codex đo lại **26–30s**.
- Vì 4 query chạy **song song**, wall-clock của endpoint ≈ **query CHẬM NHẤT**, không phải tổng. Endpoint vẫn 19–30s ⇒ **một query đơn lẻ đã mất ~20–30s**. Query nặng nhất chính là cái có full-scan `COUNT(DISTINCT CONCAT(...))` trên `silver_detections` — phần Phase 0 thêm vào.
- Thêm nữa: Trino ở đây **single-node**. Bắn 4 full-scan nặng song song vào một worker → chúng tranh CPU/memory, parallelism gần như không giúp (có khi còn tệ hơn do memory pressure). Nên dù code song song, hành vi thực ~ serialize.

**Trade-off công bằng cần ghi nhận:** fix correctness đã chuyển 4 lần exact `COUNT(DISTINCT)` full-scan lên đường nóng dashboard. Đúng hơn nhưng chậm hơn. Đây mới là chi phí latency thật, và compaction không che được nó nữa khi data lớn lên.

### 2.4. Hệ quả với Decision 1

Baseline kết luận "compaction đã giảm latency đáng kể → chưa cần mart". Bằng chứng tái lập **không ủng hộ** kết luận này: dashboard 12–19s và đang xấu đi bất kể compaction. Vấn đề SLA dashboard là **thật và chưa được giải quyết**.

---

## 3. Các quan sát khác (đồng ý với baseline)

- `gold_zone_minute_metrics = 0` và `gold_alert_events / gold_alerts = 0`: xác nhận. Phải debug input zone/window TRƯỚC khi xây zone mart. (Đồng ý Decision 3.)
- Dual lineage v1/v2 vẫn còn: đồng ý nên migrate `GoldDashboardAggregateJob` sang v2 (Decision 4). Lưu ý thêm: phần fix unique_tracks ở §1 cũng đang đọc `silver_detections` **v1** — khi migrate cần đổi luôn để tránh lệch nguồn giữa detections (gold từ v1) và unique (silver v1) so với heatmap/queue (v2).
- Không expire snapshots aggressive với streaming job: đồng ý.

---

## 4. Khuyến nghị (điều chỉnh lại thứ tự ưu tiên của Codex)

Codex xếp cache là Phase 1 *item 2*. Theo bằng chứng ở §2, **cache phải là việc ĐẦU TIÊN**, không phải compaction/mart:

1. **API caching (đòn bẩy rẻ nhất, tác động cao nhất) — làm trước.**
   Data chỉ đổi khi Vision chạy; cache TTL 60–120s cho dashboard/queue, 5–15 phút cho heatmap → người dùng thấy gần như tức thì, độc lập với chi phí Trino. Giải quyết trực tiếp triệu chứng 12–19s.

2. **Iceberg maintenance thành job ĐỊNH KỲ** (cron/Airflow), không one-shot.
   Lý do: §2.1 chứng minh compaction decay trong vài giờ. *Nhưng* (§2.2) maintenance một mình **không** sửa được dashboard — đừng kỳ vọng nó hạ latency; nó chỉ giữ file count lành mạnh cho heatmap/scan.

3. **Bỏ exact `COUNT(DISTINCT)` khỏi hot path.**
   Đây mới là mart candidate thật (không phải heatmap): một rollup `unique_tracks` theo ngày/giờ/camera tính sẵn (hoặc HLL sketch để cộng được). Sau khi có cache thì việc này hạ tải nền.

4. Debug `gold_zone_minute_metrics = 0`.

5. Quyết định migrate `GoldDashboardAggregateJob` → `silver_detections_v2` (kéo theo cả query unique ở §1).

**Heatmap mart**: đồng ý chưa cần ngay (heatmap cam_01 ~2–3s, cells=268 verify OK). Nhưng lý do đúng là *heatmap đủ nhanh*, **không phải** vì "compaction đã đủ".

---

## 5. Trạng thái git khi review

Worktree còn thay đổi chưa commit (đúng như Codex ghi chú): `analytics_queries.py`, `test_analytics_queries.py`, `.gitignore`, `pyproject.toml`, `uv.lock`; `docs/lakehouse/` untracked. Phần fix correctness nên được commit riêng (sạch, đã test).

---

## 6. Chốt lại cho người dùng

- **Giữ và commit** fix correctness của Codex — đó là kết quả thật của Phase 0. ✅
- **Sửa lại narrative trong baseline §7/§9 Decision 1**: compaction không phải đòn bẩy cho dashboard; con số 4.3s không tái lập.
- **Ưu tiên Phase 1 = API cache trước tiên**, rồi maintenance định kỳ, rồi rollup unique. Đừng nhảy vào heatmap mart.
