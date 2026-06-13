# Implementation Roadmap

Roadmap này bám theo kiến trúc đã chốt:

- `Bronze / Silver / Gold`
- `Flink` là transform engine chính
- `Airflow` là orchestrator
- `Gold serving` là nhóm bảng con của Gold, không phải tier mới

## Phase 0

Mục tiêu:

- verify pipeline hiện tại
- xác nhận bảng nào đang là Gold facts thật
- đo latency dashboard
- xác định vấn đề nào là correctness, vấn đề nào là performance

Output:

- baseline latency
- baseline file/snapshot count
- danh sách endpoint đang đọc sai tầng

## Phase 1

Mục tiêu:

- dọn analyst path về đúng mô hình
- bỏ metric không cần thiết khỏi critical path
- giữ cache và query routing gọn

Ưu tiên:

1. correctness của payload analyst
2. cache
3. query routing sang Gold facts hoặc Gold serving tối thiểu

Không làm:

- mở thêm tier kiến trúc
- build subsystem quá lớn chỉ để tối ưu sớm

## Phase 2

Mục tiêu:

- chuẩn hóa Gold facts cho analyst

Ví dụ:

- zone facts
- queue facts
- daily traffic facts
- dwell facts

Hướng ưu tiên:

- nếu logic là streaming/incremental: để Flink xử lý
- nếu logic là bounded finalize/backfill: để job batch xử lý, Airflow điều phối

## Phase 3

Mục tiêu:

- thêm Gold serving khi thật sự cần

Chỉ thêm Gold serving nếu:

- Gold facts hiện tại chưa đủ đúng grain
- query analyst còn nặng
- cache không đủ

Ví dụ phù hợp:

- heatmap history
- hourly serving cho queue/zone
- executive daily serving

## Phase 4

Mục tiêu:

- đưa Airflow vào với vai trò đúng

Airflow sẽ điều phối:

- `Silver -> Gold` batch jobs
- `Gold -> Gold serving` jobs
- maintenance Iceberg
- DQ checks
- backfill/finalize

Không dùng Airflow để:

- thay Flink realtime
- viết transform nặng trong Python

## Phase 5

Mục tiêu:

- hardening production behavior

Bao gồm:

- Airflow maintenance
- snapshot retention
- optimize hot partitions
- audit refresh
- stale-source detection

## Quy tắc ưu tiên

Khi chọn việc tiếp theo, luôn theo thứ tự:

1. fix feature hỏng
2. fix correctness
3. fix routing
4. fix maintenance
5. chỉ sau đó mới thêm serving abstraction mới

## Kết luận

Roadmap đúng cho project này không phải:

```text
Bronze -> Silver -> Gold -> Mart
```

mà là:

```text
Bronze -> Silver -> Gold
                |- Gold facts
                |- Gold serving

Airflow điều phối các batch job và maintenance quanh Gold
Flink tiếp tục xử lý streaming transforms
```
