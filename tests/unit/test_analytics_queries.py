from __future__ import annotations

from rva_api.api.v1 import analytics_queries


def test_trino_query_timeout_defaults(monkeypatch):
    monkeypatch.delenv("TRINO_QUERY_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("TRINO_QUERY_MAX_WAIT_SEC", raising=False)

    assert analytics_queries._query_timeout() == 5
    assert analytics_queries._max_query_wait() == 20


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

    assert "gold_camera_hourly_metrics" in combined_sql
    assert "gold_camera_daily_metrics" in combined_sql
    assert "gold_camera_daily_dwell" in combined_sql
    assert "silver_detections" not in combined_sql
    assert "gold_track_summary" not in combined_sql


def test_daily_query_returns_real_dwell_and_quality_fields():
    sql = analytics_queries.daily_sql(7)

    assert "avg_dwell_sec" in sql
    assert "avg_conf" in sql
    assert "unique_tracks" in sql
