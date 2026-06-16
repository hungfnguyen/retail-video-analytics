# Alignment And Revised Roadmap

Tài liệu này chốt lại việc chỉnh hướng sau khi loại bỏ nhánh over-engineering.

## Điều chỉnh chính

Trước đây phần docs đã đi theo hướng:

```text
Bronze / Silver / Gold / Mart
```

Hướng đó không còn dùng làm kiến trúc chuẩn nữa.

Kiến trúc đúng đã chốt lại là:

```text
Bronze / Silver / Gold
```

Trong `Gold` có:

- Gold facts
- Gold serving

## Vai trò công nghệ

`Flink`:
- engine chính cho streaming transforms

`Airflow`:
- orchestrator cho batch jobs, maintenance, backfill

`Trino`:
- query engine trên Iceberg snapshots

## Ý nghĩa với roadmap

Roadmap từ đây nên đọc như sau:

1. sửa correctness / feature hỏng trước
2. giữ analyst path gọn
3. chỉ thêm Gold serving khi có lý do thật
4. dùng Airflow để điều phối, không thay engine transform

## Ý nghĩa với code hiện tại

Code hiện tại nên dùng:

- `services/gold_serving/`
- `lakehouse.rva_gold_serving`
- `gold_serving_*`

Các tên này là implementation vật lý của Gold serving. Chúng không tạo thêm một medallion tier mới.

Không thêm lại `rva_mart`, `mart_*`, hoặc `mart layer` trong code mới.

## Kết luận ngắn

Từ thời điểm này, mọi tài liệu và phase mới trong `docs/lakehouse` phải bám theo:

```text
Bronze / Silver / Gold
Flink = transform engine
Airflow = orchestrator
Gold serving = nhóm bảng con của Gold
```
