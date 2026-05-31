# Flink API Guide

## Why Two Flink APIs

The project intentionally uses two Flink styles:

| Path | API | Reason |
|---|---|---|
| Lakehouse | Table API / SQL | Native Iceberg DDL/DML, SQL transformations, exactly-once table commits |
| Realtime | DataStream API | Custom parsing, validation, DLQ side output, Redis sink, low latency |

## Lakehouse Catalog Pattern

All lakehouse jobs create an Iceberg REST catalog from environment variables:

```java
cfg.put("type", "iceberg");
cfg.put("catalog-impl", "org.apache.iceberg.rest.RESTCatalog");
cfg.put("uri", getenv("ICEBERG_REST_URI", "http://iceberg-rest:8181"));
cfg.put("warehouse", ensureWarehouseSuffix(getenv("ICEBERG_WAREHOUSE", "s3://retail-video-analytics-prod/lakehouse"), "/iceberg"));
cfg.put("io-impl", "org.apache.iceberg.aws.s3.S3FileIO");
cfg.put("s3.endpoint", getenv("S3_ENDPOINT", "https://s3.ap-southeast-2.amazonaws.com"));
cfg.put("s3.path-style-access", getenv("S3_PATH_STYLE", "false"));
cfg.put("s3.region", getenv("S3_REGION", "ap-southeast-2"));
```

Credentials are read from `S3_ACCESS_KEY` / `S3_SECRET_KEY`, with AWS SDK alias variables also set in Docker Compose.

## Implemented Jobs

| Job | Class |
|---|---|
| Bronze | `org.rva.BronzeIngestJob` |
| Silver | `org.rva.silver.SilverJob` |
| Gold track summary | `org.rva.gold.GoldTrackSummaryJob` |
| Realtime metrics | `org.rva.realtime.RealtimeMetricsJob` |

## Table API Usage

Bronze reads Pulsar as raw JSON and inserts into Iceberg.

Silver reads Bronze as an Iceberg streaming source and uses `ParseDetections` UDTF.

Gold reads Silver as an Iceberg streaming source and writes upsert-enabled track summaries.

## DataStream Usage

Realtime job:

1. Reads raw JSON from Pulsar.
2. Parses and validates required fields.
3. Emits invalid events to DLQ side output.
4. Deduplicates valid events by `event_id`.
5. Writes low-latency state to Redis.

## Operational Caution

`flink run` executes job `main()` in the submitter container before the job graph is sent to the cluster. Therefore S3/Iceberg environment variables must be set consistently on:

- `flink-jobmanager`;
- `flink-taskmanager`;
- `flink-job-submitter`.

If the submitter has stale storage config, the wrong endpoint can be embedded in the job graph.
