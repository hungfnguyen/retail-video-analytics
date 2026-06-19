from __future__ import annotations

from rva_api.api.v1 import analytics_queries


def test_trino_query_timeout_defaults(monkeypatch):
    monkeypatch.delenv("TRINO_QUERY_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("TRINO_QUERY_MAX_WAIT_SEC", raising=False)

    assert analytics_queries._query_timeout() == 5
    assert analytics_queries._max_query_wait() == 60


def test_dashboard_queries_filter_by_metric_date():
    for sql in (
        analytics_queries.summary_sql(7),
        analytics_queries.hourly_sql(7),
        analytics_queries.camera_sql(7),
        analytics_queries.daily_sql(7),
    ):
        assert "metric_date >= CURRENT_DATE - INTERVAL '7' DAY" in sql


def test_dashboard_queries_read_gold_aggregate_tables():
    combined_sql = "\n".join(
        [
            analytics_queries.summary_sql(7),
            analytics_queries.hourly_sql(7),
            analytics_queries.camera_sql(7),
            analytics_queries.daily_sql(7),
        ]
    )

    assert "lakehouse.rva_gold_serving.gold_serving_traffic_hourly" in combined_sql
    assert "lakehouse.rva_gold_serving.gold_serving_traffic_daily" in combined_sql
    assert "lakehouse.rva_gold_serving.gold_serving_dwell_daily" in combined_sql
    assert "gold_camera_hourly_metrics" not in combined_sql
    assert "gold_camera_daily_metrics" not in combined_sql


def test_dashboard_queries_do_not_read_unique_track_metrics():
    combined_sql = "\n".join(
        [
            analytics_queries.summary_sql(7),
            analytics_queries.hourly_sql(7),
            analytics_queries.camera_sql(7),
            analytics_queries.daily_sql(7),
        ]
    )

    assert "unique_tracks" not in combined_sql
    assert "unique_hll" not in combined_sql
    assert "COUNT(DISTINCT CONCAT(" not in combined_sql
    assert "lakehouse.rva.silver_detections_v2" not in combined_sql


def test_heatmap_and_queue_queries_read_marts():
    heatmap_sql = analytics_queries.heatmap_presence_sql("cam_01", 1)
    queue_summary_sql = analytics_queries.queue_zone_summary_sql(7)
    queue_trend_sql = analytics_queries.queue_wait_trend_sql(7)

    assert "lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min" in heatmap_sql
    assert "SUM(detection_count)" in heatmap_sql
    assert "lakehouse.rva_gold_serving.gold_serving_queue_daily" in queue_summary_sql
    assert "unique_visitors" not in queue_summary_sql
    assert "unique_hll" not in queue_summary_sql
    assert "lakehouse.rva_gold_serving.gold_serving_queue_hourly" in queue_trend_sql


def test_daily_query_returns_dwell_and_quality_fields():
    sql = analytics_queries.daily_sql(7)

    assert "avg_dwell_sec" in sql
    assert "avg_queue_wait_sec" in sql
    assert "total_alerts" in sql
    assert "unique_tracks" not in sql
