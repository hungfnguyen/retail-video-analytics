# Airflow And Analyst Architecture

Tài liệu này chốt lại kiến trúc đúng cho tầng analyst của project.

## 1. Kết luận chính

- `Bronze / Silver / Gold` là mô hình chuẩn chính.
- `Airflow` không thay `Flink`.
- `Flink` vẫn là engine chính cho streaming transforms.
- Không nên tạo một tier `mart` tách khỏi medallion.
- Các bảng phục vụ analyst nên được xem là **Gold serving**.

## 2. Lakehouse của project nên hiểu thế nào

```text
Vision -> Pulsar -> Flink -> Bronze -> Silver -> Gold
```

Trong đó:

`Bronze`:
- raw metadata events
- lưu để audit và replay

`Silver`:
- detection rows đã parse / clean / dedup / enrich
- source of truth đã làm sạch

`Gold`:
- business facts
- aggregate facts
- serving tables cho analyst

Điểm quan trọng:

```text
Gold không chỉ có 1 loại bảng.
Gold có thể gồm:
  - Gold facts gần realtime
  - Gold serving tables cho analyst/dashboard
```

Vì vậy không cần tách thêm một tier `mart` độc lập về mặt kiến trúc.

## 3. Vai trò đúng của Flink

`Flink` là transform engine cho stream.

Phần nên để Flink xử lý:

- Pulsar -> Bronze
- Bronze -> Silver
- Silver -> Gold facts gần realtime
- các job stateful / incremental / event-time

Ví dụ phù hợp với Flink:

- detection normalization
- track aggregation
- queue session
- zone occupancy
- rolling aggregates
- realtime Redis state

## 4. Vai trò đúng của Airflow

`Airflow` là workflow orchestrator.

Airflow nên làm:

- schedule job
- chain dependency giữa job
- retry / alert
- backfill theo date range
- chạy maintenance Iceberg
- chạy data quality checks

Airflow không nên:

- consume stream liên tục
- thay Flink realtime
- làm transform nặng trong Python task

## 5. Quan hệ giữa Flink và Airflow

Mô hình production hợp lý cho project này là hybrid:

```text
Streaming path:
Pulsar -> Flink -> Bronze / Silver / Gold facts

Batch serving path:
Airflow -> batch job -> Gold serving
```

Batch job mà Airflow điều phối có thể là:

- Flink batch/SQL job
- Trino SQL job
- Spark job
- dbt job

Tức là:

```text
Airflow = điều phối
Flink / Trino / Spark = thực thi transform
```

## 6. Gold serving là gì

`Gold serving` là nhóm bảng bên trong Gold được tối ưu cho analyst/dashboard.

Ví dụ:

- hourly traffic
- daily camera metrics
- heatmap history
- queue hourly summary
- zone daily summary

Chúng vẫn là Gold vì:

- không còn là raw fact
- đã business-ready
- phục vụ query trực tiếp

## 7. Khác gì với data warehouse truyền thống

Ở data warehouse truyền thống:

- Airflow điều phối ETL/ELT qua staging -> core -> mart

Ở project này:

- Flink materialize liên tục `Bronze -> Silver -> Gold`
- Airflow điều phối phần batch serving và maintenance

Điểm giống:

- analyst không nên query raw tables
- serving table nên có refresh logic rõ
- maintenance và backfill cần orchestrator

Điểm khác:

- nền ingest và transform thấp tầng của project là streaming-first

## 8. Kiến trúc mục tiêu

```text
Vision / Camera
    -> Pulsar
    -> Flink streaming transforms
    -> Bronze / Silver / Gold facts

Gold facts
    -> batch serving job
    -> Gold serving tables
    -> Trino
    -> FastAPI cache
    -> Analyst UI
```

## 9. Quyết định cho project này

Với project Retail Video Analytics, hướng đúng là:

1. Giữ `Bronze / Silver / Gold` làm taxonomy chính.
2. Đổi toàn bộ narrative `mart layer` thành `Gold serving`.
3. Để Flink tiếp tục chịu trách nhiệm streaming transforms.
4. Dùng Airflow sau này để điều phối batch serving jobs và maintenance.
5. Không mở thêm một medallion tier mới chỉ để phục vụ dashboard.
