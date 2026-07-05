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


def test_dashboard_queries_use_unique_track_metrics_for_visitor_views():
    combined_sql = "\n".join(
        [
            analytics_queries.summary_sql(7),
            analytics_queries.hourly_sql(7),
            analytics_queries.camera_sql(7),
            analytics_queries.daily_sql(7),
        ]
    )

    assert "unique_tracks" in combined_sql
    assert "unique_hll" not in combined_sql
    assert "lakehouse.rva_gold_serving.gold_serving_traffic_daily" in combined_sql


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
    assert "total_visitors" in sql
    assert "unique_tracks" in sql


def test_dashboard_queries_accept_camera_filter():
    combined_sql = "\n".join(
        [
            analytics_queries.summary_sql(7, "cam_01"),
            analytics_queries.hourly_sql(7, "cam_01"),
            analytics_queries.daily_sql(7, "cam_01"),
            analytics_queries.visitors_series_sql(7, "cam_01"),
            analytics_queries.weekday_pattern_sql(7, "cam_01"),
            analytics_queries.peak_heatmap_sql(7, "cam_01"),
            analytics_queries.top_zones_sql(7, "cam_01"),
            analytics_queries.dwell_trend_sql(7, "cam_01"),
        ]
    )

    assert "camera_id = 'cam_01'" in combined_sql
    camera_daily_sql = analytics_queries.daily_sql(7, "cam_01")
    assert "avg_confidence" in camera_daily_sql
    assert "gold_serving_executive_daily" not in camera_daily_sql


def test_queue_and_alert_queries_accept_camera_filter():
    assert "camera_id = 'cam_02'" in analytics_queries.queue_zone_summary_sql(7, "cam_02")
    assert "camera_id = 'cam_02'" in analytics_queries.queue_wait_trend_sql(7, "cam_02")
    assert "camera_id = 'cam_02'" in analytics_queries.alerts_history_sql(7, "cam_02")


def test_alert_history_queries_read_direct_history_table():
    sql = analytics_queries.alerts_history_sql(7)

    assert analytics_queries.ALERT_HISTORY_TABLE in sql
    assert "gold_alerts" not in sql
    assert "from_iso8601_timestamp(event_ts)" in sql


def test_insert_alert_history_sql_uses_iso8601_date_projection():
    sql = analytics_queries.insert_alert_history_sql(
        {
            "alert_id": "a1",
            "camera_id": "cam_01",
            "store_id": "store_001",
            "alert_type": "queue_overcrowded",
            "severity": "high",
            "title": "Queue overcrowded",
            "description": "2 people waiting",
            "zone": "checkout_queue_02",
            "event_ts": "2026-07-05T05:58:18.296374+00:00",
            "clip_s3_key": None,
            "snapshot_key": "snapshots/cam_01/a1.jpg",
        }
    )

    assert "from_iso8601_timestamp('2026-07-05T05:58:18.296374+00:00')" in sql
    assert "INSERT INTO lakehouse.rva.gold_alert_history" in sql
