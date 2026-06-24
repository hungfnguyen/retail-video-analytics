from __future__ import annotations

from rva_api.api.v1 import analytics


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


def test_dashboard_ready_response_uses_cache(monkeypatch):
    cache = FakeCache()
    calls = {"count": 0}

    def fake_dashboard_queries(days: int, camera_id: str | None = None):
        calls["count"] += 1
        return {
            "summary": [[100, 1, 0.8, 100.0, 12.0, 1, 2, 3, 25]],
            "hourly": [["10:00", 25, 25, 100]],
            "camera": [["cam_01", 100, 100.0, 0.8]],
            "daily": [["2026-06-12", 25, 100, "10:00", 12.0, 0.8, 0.0, 0]],
        }, {}

    monkeypatch.setattr(analytics, "_get_cache_client", lambda: cache)
    monkeypatch.setattr(analytics, "_run_dashboard_queries", fake_dashboard_queries)

    first = analytics.get_analytics_dashboard(7)
    second = analytics.get_analytics_dashboard(7)

    assert calls["count"] == 1
    assert first.generated_at == second.generated_at
    assert cache.ttls["analytics:cache:v2:dashboard:days_7"] == analytics.DASHBOARD_CACHE_TTL_SEC


def test_dashboard_error_response_is_not_cached(monkeypatch):
    cache = FakeCache()
    calls = {"count": 0}

    def fake_dashboard_queries(days: int, camera_id: str | None = None):
        calls["count"] += 1
        return {}, {"summary": "boom"}

    monkeypatch.setattr(analytics, "_get_cache_client", lambda: cache)
    monkeypatch.setattr(analytics, "_run_dashboard_queries", fake_dashboard_queries)

    first = analytics.get_analytics_dashboard(7)
    second = analytics.get_analytics_dashboard(7)

    assert calls["count"] == 2
    assert first.data_status == "error"
    assert second.data_status == "error"
    assert "analytics:cache:v2:dashboard:days_7" not in cache.ttls


def test_dashboard_camera_response_uses_camera_cache_key(monkeypatch):
    cache = FakeCache()
    captured: list[str | None] = []

    def fake_dashboard_queries(days: int, camera_id: str | None = None):
        captured.append(camera_id)
        return {
            "summary": [[25, 1, 0.75, 25.0, 10.0, 1, 2, 3, 12]],
            "hourly": [["10:00", 12, 12, 25]],
            "camera": [["cam_01", 25, 100.0, 0.75]],
            "daily": [["2026-06-16", 12, 25, "10:00", 10.0, 0.75, 5.5, 2]],
        }, {}

    monkeypatch.setattr(analytics, "_get_cache_client", lambda: cache)
    monkeypatch.setattr(analytics, "_run_dashboard_queries", fake_dashboard_queries)

    first = analytics.get_analytics_dashboard(7, "cam_01")
    second = analytics.get_analytics_dashboard(7, "cam_01")

    assert captured == ["cam_01"]
    assert first.generated_at == second.generated_at
    assert first.daily_summary[0].avg_confidence == 0.75
    assert first.daily_summary[0].avg_queue_wait_sec == 5.5
    assert first.daily_summary[0].alerts == 2
    assert first.daily_summary[0].visitors == 12
    assert first.peak_hour.visitors == 12
    assert cache.ttls["analytics:cache:v2:dashboard:days_7:camera_cam_01"] == analytics.DASHBOARD_CACHE_TTL_SEC


def test_analytics_error_message_identifies_gold_serving_schema():
    message = analytics._analytics_error_message(
        RuntimeError("Schema 'rva_gold_serving' does not exist")
    )

    assert message.startswith("Gold serving schema unavailable:")


def test_analytics_error_message_identifies_gold_serving_table():
    message = analytics._analytics_error_message(
        RuntimeError("Table 'gold_serving_traffic_daily' not found")
    )

    assert message.startswith("Gold serving table unavailable:")


def test_queue_ready_response_uses_cache(monkeypatch):
    cache = FakeCache()
    calls = {"count": 0}

    def fake_trino_query(sql: str, max_wait: float | None = None):
        calls["count"] += 1
        if "gold_serving_queue_daily" in sql and "GROUP BY queue_zone_id" in sql:
            return [["checkout_queue_01", 4, 15.5, 30.0]]
        return [["10:00", 15.5, 4]]

    monkeypatch.setattr(analytics, "_get_cache_client", lambda: cache)
    monkeypatch.setattr(analytics, "trino_query", fake_trino_query)

    first = analytics.get_queue_analytics(7)
    second = analytics.get_queue_analytics(7)

    assert calls["count"] == 2
    assert first.generated_at == second.generated_at
    assert cache.ttls["analytics:cache:v2:queue:days_7"] == analytics.QUEUE_CACHE_TTL_SEC


def test_heatmap_empty_response_uses_short_cache_ttl(monkeypatch):
    cache = FakeCache()
    calls = {"count": 0}

    def fake_trino_query(sql: str, max_wait: float | None = None):
        calls["count"] += 1
        return []

    monkeypatch.setattr(analytics, "_get_cache_client", lambda: cache)
    monkeypatch.setattr(analytics, "trino_query", fake_trino_query)

    first = analytics.get_presence_heatmap("cam_01", 1, "presence")
    second = analytics.get_presence_heatmap("cam_01", 1, "presence")

    assert calls["count"] == 1
    assert first.data_status == "empty"
    assert second.generated_at == first.generated_at
    assert cache.ttls["analytics:cache:v2:heatmap:cam_01:days_1:metric_presence"] == analytics.EMPTY_RESULT_CACHE_TTL_SEC
