# Evaluation Plan

## Evaluation Goals

The evaluation should prove that the implemented pipeline is correct, observable, and performant enough for a local thesis/demo environment.

## Functional Checks

| Area | Check |
|---|---|
| Vision | Events are published and live frames are updated |
| Pulsar | Topics exist and receive messages |
| Flink | Four jobs are running |
| Redis | Live count, heatmap, active tracks, latest frame keys exist |
| Iceberg | Bronze/Silver/Gold tables have rows |
| Trino | Queries return expected counts |
| FastAPI | Live dashboard endpoint returns schema-valid data |
| Frontend | Live page displays video and metrics |
| AWS S3 | Lakehouse path exists; sampled frames exist when enabled |

## Data Quality Checks

```sql
SELECT COUNT(*) FROM lakehouse.rva.bronze_raw;
SELECT COUNT(*) FROM lakehouse.rva.silver_detections_v2;
SELECT COUNT(*) FROM lakehouse.rva.gold_track_summary_v2;
SELECT COUNT(*) FROM lakehouse.rva.gold_queue_sessions;

SELECT camera_id, COUNT(*)
FROM lakehouse.rva.silver_detections_v2
GROUP BY camera_id;

SELECT camera_id, COUNT(*) AS tracks, AVG(duration_sec)
FROM lakehouse.rva.gold_track_summary_v2
GROUP BY camera_id;

SHOW TABLES FROM lakehouse.rva_gold_serving;
```

Expected properties:

- Silver rows should not exceed invalid parsing expectations.
- `camera_id` and `store_id` should be present in all curated rows.
- `conf` in Silver v2 should satisfy the current configured lakehouse filter.
- Gold track summaries should have non-negative duration and positive frame counts.

## Latency Metrics

| Metric | How to measure |
|---|---|
| Media latency | `frame.media_latency_ms` in live dashboard API |
| Metadata latency | `frame.metadata_latency_ms` in live dashboard API |
| Realtime state freshness | Redis TTL and API status fields |
| Lakehouse availability | Time from Vision start to rows visible in Trino |
| Query latency | Shell time around Trino queries |

## Reliability Tests

- Restart FastAPI while Vision and Flink keep running.
- Stop Vision and verify dashboard becomes stale instead of showing fresh data.
- Produce an invalid event and verify DLQ receives it.
- Restart Flink containers and verify jobs recover or resubmit cleanly.
- Temporarily block S3 credentials in a test environment and verify Iceberg write failures are visible in Flink exceptions.

## Reporting

For thesis/demo reporting, include:

- service status screenshot or CLI output;
- Trino row-count queries;
- Redis key samples;
- frontend Live screenshot;
- S3 object listing;
- known limitations and next roadmap items.
