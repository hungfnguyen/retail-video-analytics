# Alignment Check & Revised Roadmap — Analyst Lakehouse

Người đánh giá: Claude (Opus 4.8)
Ngày: 2026-06-12
Câu hỏi cần trả lời: bộ docs `docs/lakehouse/` có đang đi đúng yêu cầu **"làm lại tầng analyst tối ưu, chuẩn DE, KHÔNG over-engineering"** không, và bước tiếp theo nên làm gì?

---

## 1. Kết luận thẳng

| | Đánh giá |
|---|---|
| **Phần đã CODE** (Phase 0 fix + Phase 1.1 cache) | ✅ **Đúng hướng, lean, chuẩn DE.** Sửa correctness + cache là 2 việc rẻ nhất/đúng nhất. |
| **Phần roadmap đã VIẾT** (docs 01–05) | ⚠️ **Over-engineering cho scale hiện tại.** Viết *trước* khi có kết quả cache, nên kê đơn quá nặng. |

Nói gọn: **đang làm đúng, nhưng kế hoạch trên giấy thì thừa.** Docs 01–05 mô tả kiến trúc maximalist (Airflow + 5 DAG + **13 bảng mart** + data quality framework + backfill DAG). Ở **88K rows**, nơi mà **một lớp cache đã cho 1900x**, xây 13 mart + full Airflow là thừa — trừ khi luận văn *cố ý* muốn trình diễn orchestration.

---

## 2. Bằng chứng vì sao roadmap cũ là thừa

Từ Phase 0 + Phase 1.1 (đã verify, không phải giả định):

1. **Scale nhỏ**: silver ~88K rows. Đây là quy mô laptop, không phải warehouse.
2. **Small files KHÔNG phải nút thắt**: re-OPTIMIZE về 1 file mà dashboard vẫn 12–30s ⇒ compaction không phải đòn bẩy.
3. **Cache mới là đòn bẩy thật**: dashboard 7.2s → **0.004s** hot. Người dùng poll 30s gần như luôn trúng hot.
4. **Heatmap vốn đã nhanh**: cold ~2s, cached ~5ms. **Không cần `mart_heatmap_*`.**

→ Hệ quả: phần lớn giá trị mà 13 mart hứa hẹn (giảm latency dashboard/heatmap) đã đạt được bằng cache với chi phí ~150 dòng code. Mart chỉ còn ý nghĩa cho *cold path* và *scale tương lai* — không phải nhu cầu hiện tại.

---

## 3. Sai lệch ưu tiên nghiêm trọng nhất trong roadmap cũ

Roadmap (05) xếp **"build heatmap mart" là Phase 2** (việc lớn đầu tiên). Nhưng:

- Heatmap **đã nhanh** (không cần mart).
- Trong khi đó **`gold_zone_minute_metrics = 0` và `gold_alert_events / gold_alerts = 0`** — tức **Zone analytics và Alert history là feature ĐANG HỎNG, không có dữ liệu.**

→ Roadmap đang đề xuất tối ưu cái đã nhanh, trong khi **bỏ qua feature đang chết**. Đây là sai lệch ưu tiên kinh điển. Một DE đúng nghĩa phải **sửa cái hỏng trước khi tối ưu cái đã chạy**.

---

## 4. Phân loại việc theo lăng kính "no over-engineering"

### 🔴 MUST — sửa cái đang hỏng (ưu tiên cao nhất, KHÔNG phải mart)

1. **Debug `gold_zone_minute_metrics = 0`** → Zone analytics không có data. Kiểm tra `silver_detections_v2.primary_zone_id/zone_type` có giá trị không; `QueueAnalyticsJob` window/group có đúng không.
2. **Debug `gold_alert_events = 0` và `gold_alerts = 0`** → Alert history rỗng. Xác nhận có alert thật được sinh không, hay job aggregate sai.

### 🟡 SHOULD — hardening lean (rẻ, đúng DE)

3. **Maintenance định kỳ = cron + script Trino**, KHÔNG Airflow. 1 container nhẹ chạy `OPTIMIZE` hot tables mỗi 2–6h + log file count. Lý do: Phase 0 chứng minh compaction decay trong vài giờ; cần định kỳ để giữ scan lành mạnh. (~30 dòng bash/python.)
4. **Chốt dual lineage v1/v2**: migrate `GoldDashboardAggregateJob` (+ query unique ở `analytics_queries.py`) sang `silver_detections_v2`, hoặc document v1 là dependency bắt buộc. Rủi ro maintainability, không phải perf.

### 🟢 OPTIONAL — chỉ làm khi có lý do cụ thể

5. **Rollup `unique_tracks`** (1 bảng daily/hourly aggregate): gỡ exact `COUNT(DISTINCT)` khỏi cold path. **Nhưng cache đã che chi phí này** (chỉ trả 1 lần / TTL). Chỉ làm nếu cold latency thật sự gây khó chịu khi demo, hoặc nếu muốn 1 ví dụ mart "thật" cho luận văn. Đây là mart candidate **đáng giá nhất** nếu phải chọn 1.

### ⚫ DON'T — over-engineering ở scale này

- 13 bảng mart (`mart_traffic_*`, `mart_heatmap_*`, `mart_zone_*`, `mart_queue_*`, `mart_dwell_*`, `mart_alert_*`, `mart_executive_daily`).
- 5 Airflow DAG + backfill DAG + full data-quality framework.
- Rewrite query routing để "dashboard không bao giờ đọc Silver".

→ Tất cả đều đúng *về lý thuyết warehouse*, nhưng không tạo giá trị đo được ở 88K rows. Để dành cho "future work" trong luận văn.

---

## 5. Góc luận văn (quan trọng — đừng bỏ Airflow một cách máy móc)

Bạn là DE student, luận văn tốt nghiệp. Airflow/mart có **giá trị trình diễn năng lực**, kể cả khi không cần cho performance. Nhưng "trình diễn" ≠ "build 13 mart". Nếu hội đồng/đề tài cần thấy orchestration:

> Làm **bản tối thiểu**: 1 Airflow (compose profile riêng, LocalExecutor) chạy **1 DAG** gồm: maintenance (mục 3) + refresh **1 mart** (rollup unique_tracks ở mục 5) + ghi audit. Đủ kể câu chuyện "Flink near-real-time + Airflow batch orchestration + Iceberg maintenance" mà không phình scope/RAM.

Đây là cách dung hòa "chuẩn DE" với "không over-engineering" cho bối cảnh thesis.

---

## 6. Bước tiếp theo đề xuất (thứ tự thực dụng)

```
1. [MUST]   Debug gold_zone_minute_metrics = 0  (Zone analytics đang chết)
2. [MUST]   Debug gold_alert_events / gold_alerts = 0  (Alert history đang chết)
3. [SHOULD] Cron maintenance: OPTIMIZE hot tables định kỳ + log file count
4. [SHOULD] Chốt + thực thi lineage v1 -> v2 cho dashboard
5. [OPT]    Rollup unique_tracks (nếu cold latency làm phiền, hoặc cần 1 mart demo)
6. [OPT/thesis] Airflow tối thiểu 1 DAG bọc (3)+(5)+audit — chỉ khi luận văn cần
```

**Không** bắt đầu từ heatmap mart. **Không** build 13 mart. **Không** bật Airflow chung với live demo 3 camera (RAM 15GB).

---

## 7. Đề xuất với docs hiện tại

- Docs 01–05 **giữ lại làm "target architecture / future work"** — chúng đúng về lý thuyết và có giá trị cho chương kiến trúc của luận văn.
- Nhưng `05_IMPLEMENTATION_ROADMAP.md` đang dẫn dắt sai thứ tự (heatmap mart trước, bỏ qua feature hỏng). Nên **thêm 1 callout ở đầu 05** trỏ sang doc này: "ưu tiên thực thi đã được điều chỉnh sau Phase 0/1 — xem ALIGNMENT_AND_REVISED_ROADMAP". (Chưa sửa, chờ bạn duyệt.)
