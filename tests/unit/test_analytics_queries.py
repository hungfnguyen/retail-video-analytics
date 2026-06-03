from __future__ import annotations

from rva_api.api.v1 import analytics_queries


def test_trino_query_timeout_defaults(monkeypatch):
    monkeypatch.delenv("TRINO_QUERY_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("TRINO_QUERY_MAX_WAIT_SEC", raising=False)

    assert analytics_queries._query_timeout() == 5
    assert analytics_queries._max_query_wait() == 20


def test_gold_queries_filter_by_partition_date():
    for sql in (
        analytics_queries.dwell_sql(7),
        analytics_queries.avg_dwell_sql(7),
    ):
        assert "visit_date >= CURRENT_DATE - INTERVAL '7' DAY" in sql


def test_daily_query_avoids_gold_table():
    sql = analytics_queries.daily_sql(7)

    assert "gold_track_summary" not in sql
