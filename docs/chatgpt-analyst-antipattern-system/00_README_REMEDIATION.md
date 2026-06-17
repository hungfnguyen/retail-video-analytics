# Remediation Plan — Antipattern & Technical Debt

Bộ tài liệu này là **kế hoạch sửa hệ thống** sau khi đối chiếu 2 phân tích của ChatGPT
(`system.md`, `partition-strateric.md`) với **code thực tế** của repo.

Mục tiêu: xác định đúng cái gì là antipattern/technical debt **thật**, cái gì là
**nói quá / lỗi thời**, rồi đưa ra lộ trình sửa **hợp lý theo scope đồ án** — ưu tiên
correctness, đẩy production-hardening vào "Future Work" thay vì over-engineering.

> Nguyên tắc nền: dự án đã chốt bỏ nhánh over-engineering (xem
> `docs/lakehouse/ALIGNMENT_AND_REVISED_ROADMAP_2026-06-12.md`). Remediation này
> phải **không** kéo lại độ phức tạp đã bỏ. Mọi đề xuất đều ghi rõ: *nên làm trong
> đồ án* hay *chỉ ghi vào luận văn như giới hạn/đề xuất tương lai*.

## Cách dùng bộ tài liệu

| File | Nội dung |
|---|---|
| `00_README_REMEDIATION.md` | File này — index, scope, verdict tổng |
| `01_VERIFICATION_OF_ANALYSIS.md` | Đối chiếu từng claim của ChatGPT với code (`file:line`): đúng / sai / lỗi thời / bỏ sót |
| `02_REMEDIATION_PLAN.md` | Lộ trình sửa phân tầng P0/P1/P2 + Future Work, mỗi item: vấn đề → bằng chứng → cách sửa → effort → có nên làm trong đồ án |
| `03_PARTITION_REDESIGN.md` | Quyết định về partition strategy: cái gì sửa thật, cái gì để future work, kèm DDL đề xuất tối thiểu |
| `04_FINAL_TECH_DEBT_ASSESSMENT.md` | Kết luận cuối cùng sau khi đối chiếu tài liệu với trạng thái code hiện tại: debt thật, debt đã stale, mức ưu tiên |
| `05_IMPLEMENTATION_PHASES.md` | Kế hoạch triển khai theo phase: làm gì, file nào chạm, output cần có, tiêu chí verify |
| `06_PROGRESS_2026-06-14.md` | Nhật ký ngắn gọn các bước remediation đã làm xong trong code và output runtime đã verify |

> **Source of truth để triển khai:** đọc `04_FINAL_TECH_DEBT_ASSESSMENT.md` trước, sau đó dùng
> `05_IMPLEMENTATION_PHASES.md` làm checklist thực hiện. Các file `system.md` và
> `partition-strateric.md` là phân tích thô ban đầu; `01`-`03` là phần verify/đính chính chi tiết.

## Verdict tổng quan

1. **Kiến trúc tổng thể đúng hướng.** Tách `streaming realtime path` (Redis) khỏi
   `batch finalized path` (Iceberg/Flink batch) là tư duy production hợp lý. Medallion
   Bronze/Silver/Gold đúng chuẩn.

2. **Phân tích của ChatGPT phần lớn CHÍNH XÁC** — đa số claim verify được bằng code thật,
   không phải nhận xét generic. Chi tiết ở `01_*`.

3. **Nhưng có sai sót cần đính chính:**
   - Claim *"SequentialExecutor không chạy song song"* đã **lỗi thời** — repo hiện dùng
     `LocalExecutor` + Postgres (`docker-compose.yml:290`).
   - Claim *"Bronze partition là antipattern lớn nhất"* **nói quá** — Bronze hiện không bị
     query theo ngày (Silver đọc nó bằng streaming incremental).
   - Lo ngại pruning `days(capture_ts)` **hơi quá** với Trino; vấn đề thật là **timezone /
     business_date**, không phải bản thân transform `days()`.

4. **ChatGPT bỏ sót điểm state nặng nhất:** dedup `ROW_NUMBER()` ở `SilverJob` cũng là
   **unbounded streaming state** (giữ state cho mọi `(event_id, det_id)`), phình nhanh hơn
   cả các `GROUP BY` Gold mà ChatGPT cảnh báo.

5. **Debt đáng sửa trong đồ án (correctness) ≠ debt production-hardening.** Đừng nhầm hai
   loại. Xem phân tầng ở `02_*`.

## Tóm tắt phân tầng (chi tiết ở `02_REMEDIATION_PLAN.md`)

```
P0 — Correctness (NÊN sửa trong đồ án, rẻ, ảnh hưởng tính đúng của số liệu):
  1. parseCaptureMs fallback currentTime  → làm sai partition/KPI ngày
  2. executive_daily: dependency Airflow ≠ nguồn SQL thực
  3. Unbounded streaming state (Silver dedup + Gold group-by) → set state TTL
  4. Audit table có code nhưng không ghi → hoàn thiện writeAudit
  5. Chốt semantics idempotency cho serving refresh → DELETE window + INSERT INTO

P1 — Consistency / debt vừa (NÊN làm nếu còn thời gian):
  6. Chọn 1 source of truth Gold serving: bỏ dần Trino path
  7. Sửa comment/doc còn nhắc SequentialExecutor (đã là LocalExecutor)
  8. Tách DDL/catalog bootstrap khỏi runtime job (IcebergCatalogSupport)
  9. Move SQL khỏi Java string → file resource
  10. Thêm DLQ cho Silver parse errors

P2 / Future Work — Production hardening (GHI vào luận văn, KHÔNG bắt buộc code):
  - Checkpoint/savepoint lên S3/MinIO
  - Tách cluster streaming vs batch (hoặc Airflow pool)
  - Cancel Flink job khi Airflow timeout
  - 1 jar versioned thay vì copy nhiều tên
  - Parallelism sizing, Redis metrics/pipeline
  - Partition redesign business_date + store_id (xem 03_*)
```

## Lưu ý vận hành

Theo quy ước dự án, **assistant chỉ đề xuất** — các bước build / restart stack / trigger DAG
do người dùng tự chạy. Bộ tài liệu này là *kế hoạch*, không phải nhật ký thay đổi code.
