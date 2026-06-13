# Implementation Roadmap

This roadmap starts from the current implemented system and lists the next practical work items.

## Current Baseline

Implemented:

- Vision multi-camera processing.
- Pulsar metadata topics.
- Flink Bronze/Silver v2/Gold facts lakehouse path.
- Flink Gold dashboard aggregate tables for hourly, daily, and dwell analytics.
- Flink queue sessions and clip-backed alert history.
- Flink realtime Redis/DLQ path.
- Gold serving tables backed by Trino SQL runners.
- FastAPI analytics endpoints backed by Trino and cache.
- Airflow orchestration skeleton for Gold serving refresh and Iceberg maintenance.
- AWS S3-backed Iceberg warehouse.
- Trino query access.
- FastAPI live dashboard and media serving.
- React Live, Analytics, Heatmap, and System pages.

## Phase 1: Documentation Alignment

- Keep docs as as-built documentation.
- Remove stale architecture references.
- Keep README/run guide aligned with current commands.
- Document current table names and topic names only.

## Phase 2: Lakehouse Analytics Expansion

Remaining analytical Gold tables should be added based on clear dashboard needs:

- line-crossing / funnel history;
- store-level daily rollups across all cameras;
- data quality daily summary.

Each new table should include:

- schema definition;
- Flink or batch job owner;
- validation query;
- frontend/API use case.

## Phase 3: Analytics API Refinement

Current analytics endpoints already exist. Add narrower FastAPI endpoints backed by Trino when drill-down workflows need them:

```text
GET /api/v1/analytics/hourly-traffic
GET /api/v1/analytics/camera-comparison
GET /api/v1/analytics/track-summary
GET /api/v1/analytics/heatmap
```

Requirements:

- bounded date range;
- camera/store filters;
- query timeout;
- response schema tests.

## Phase 4: System Health API

Add health checks for:

- Redis;
- FastAPI;
- Pulsar broker/admin;
- Flink jobs;
- Iceberg REST;
- Trino;
- AWS S3 access.

The System page should stop using static throughput/log data once these endpoints exist.

## Phase 5: Alert Data Product

Define alert source and retention:

- realtime high-density alerts;
- camera stale/offline alerts;
- DLQ/error alerts;
- optional clip artifact linkage.

Store alert history in the lakehouse or a small API-managed event table only after the contract is fixed.

## Phase 6: Evaluation

Measure:

- camera-to-browser media latency;
- Pulsar-to-Redis latency;
- lakehouse commit latency;
- Trino query latency;
- S3 object write success;
- GPU/CPU resource usage.
