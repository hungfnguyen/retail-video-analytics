# Lakehouse Architecture

Bộ tài liệu này mô tả kiến trúc lakehouse chuẩn cho project Retail Video Analytics theo kết luận đã chốt:

1. `Bronze / Silver / Gold` vẫn là mô hình chính.
2. `Airflow` là orchestrator, không phải transform engine.
3. `Flink` giữ vai trò chính cho streaming transforms.
4. Bảng analyst-serving là một nhóm bảng **Gold serving**, không phải tier `mart` độc lập.
5. Airflow sau này sẽ điều phối job batch cho `Silver -> Gold`, `Gold -> Gold serving`, và maintenance Iceberg.

## Cách đọc bộ docs

| Tài liệu | Mục đích |
|---|---|
| [00_EXECUTION_RULES.md](00_EXECUTION_RULES.md) | Guardrails để tránh phình scope và over-engineering khi làm phase mới |
| [01_AIRFLOW_ANALYST_ARCHITECTURE.md](01_AIRFLOW_ANALYST_ARCHITECTURE.md) | Chốt vai trò của Flink, Airflow, Trino và Gold serving |
| [02_BI_MART_TABLE_DESIGN.md](02_BI_MART_TABLE_DESIGN.md) | Thiết kế lại serving model theo hướng `Gold serving`, không tách thành tier mới |
| [03_AIRFLOW_DAGS_AND_OPERATIONS.md](03_AIRFLOW_DAGS_AND_OPERATIONS.md) | Cách Airflow điều phối batch jobs, refresh và maintenance |
| [04_QUERY_ROUTING_CACHE_AND_PERFORMANCE.md](04_QUERY_ROUTING_CACHE_AND_PERFORMANCE.md) | Quy tắc query routing, cache, performance, maintenance |
| [05_IMPLEMENTATION_ROADMAP.md](05_IMPLEMENTATION_ROADMAP.md) | Roadmap triển khai theo phase |
| [06_JOB_MAPPING_AND_DATA_MODELING.md](06_JOB_MAPPING_AND_DATA_MODELING.md) | Mapping rõ job nào là Flink streaming, Flink batch, Trino SQL và Airflow orchestration |
| [07_GOLD_SERVING_PHYSICAL_MODEL.md](07_GOLD_SERVING_PHYSICAL_MODEL.md) | Chốt physical model của Gold serving và tiêu chí Trino SQL vs Flink batch |
| [ALIGNMENT_AND_REVISED_ROADMAP_2026-06-12.md](ALIGNMENT_AND_REVISED_ROADMAP_2026-06-12.md) | Tóm tắt điều chỉnh roadmap sau khi loại bỏ hướng over-engineering |

## Mô hình kiến trúc

```text
Vision / Camera
    -> Pulsar
    -> Flink streaming jobs
    -> Bronze / Silver / Gold trên Iceberg + S3

Gold facts
    -> Gold serving batch jobs
    -> Trino
    -> FastAPI cache
    -> React analyst UI
```

## Ý chính cần giữ

`Bronze`:
- raw events
- audit, replay, lineage

`Silver`:
- clean, normalize, dedup, enrich
- detection-level fact ổn định

`Gold`:
- business facts
- aggregate facts
- serving-ready facts

`Gold serving` là:
- hourly traffic
- daily camera/store metrics
- heatmap history
- queue/hourly serving tables
- zone serving tables

Những bảng này vẫn thuộc **Gold**, chỉ khác là chúng được tối ưu cho analyst/query serving.

## Vai trò công nghệ

`Flink`:
- xử lý stream liên tục
- materialize `Bronze -> Silver -> Gold`
- phù hợp với realtime/incremental/stateful transforms

`Airflow`:
- chỉ điều phối workflow hữu hạn
- schedule
- retry
- dependency
- backfill
- maintenance

`Trino`:
- query engine
- đọc snapshot Iceberg đã commit
- không thay Flink

## Lưu ý về các phase docs

Các file trong `phase0/` và `phase1/` là lịch sử triển khai và review. Chúng hữu ích để xem quyết định nào đã thử, cái gì fail, cái gì giữ lại.

Tuy nhiên, **nguồn kiến trúc chính thức** cho project hiện tại là `README` và bộ `01`–`05`, không phải các phase docs cũ.
