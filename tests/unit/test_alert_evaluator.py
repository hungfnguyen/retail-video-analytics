from __future__ import annotations

from rva_api import alert_evaluator


class FakePipeline:
    def __init__(self, client: "FakeRedis") -> None:
        self.client = client
        self.ops: list[tuple[str, tuple, dict]] = []

    def hset(self, key: str, *args, **kwargs):
        self.ops.append(("hset", (key, *args), kwargs))
        return self

    def expire(self, key: str, ttl: int):
        self.ops.append(("expire", (key, ttl), {}))
        return self

    def zadd(self, key: str, mapping: dict[str, float]):
        self.ops.append(("zadd", (key, mapping), {}))
        return self

    def zremrangebyrank(self, key: str, start: int, stop: int):
        self.ops.append(("zremrangebyrank", (key, start, stop), {}))
        return self

    def set(self, key: str, value: int, ex: int):
        self.ops.append(("set", (key, value, ex), {}))
        return self

    def execute(self):
        results = []
        for name, args, kwargs in self.ops:
            results.append(getattr(self.client, f"_apply_{name}")(*args, **kwargs))
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.values: dict[str, int] = {}

    def exists(self, key: str) -> bool:
        return key in self.values

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)

    def hset(self, key: str, field: str, value: str) -> None:
        self.hashes.setdefault(key, {})[field] = value

    def _apply_hset(self, key: str, *args, **kwargs):
        if "mapping" in kwargs:
            self.hashes.setdefault(key, {}).update(kwargs["mapping"])
            return 1
        field, value = args
        self.hashes.setdefault(key, {})[field] = value
        return 1

    def _apply_expire(self, key: str, ttl: int):
        return 1

    def _apply_zadd(self, key: str, mapping: dict[str, float]):
        self.zsets.setdefault(key, {}).update(mapping)
        return 1

    def _apply_zremrangebyrank(self, key: str, start: int, stop: int):
        return 0

    def _apply_set(self, key: str, value: int, ex: int):
        self.values[key] = value
        return True


def test_write_clip_alert_persists_density_business_alert(monkeypatch):
    client = FakeRedis()
    written_history: list[dict[str, str]] = []

    monkeypatch.setattr(alert_evaluator, "_upload_snapshot", lambda cam, aid: f"snapshots/{cam}/{aid}.jpg")
    monkeypatch.setattr(
        alert_evaluator,
        "_write_alert_history",
        lambda record, history_client: written_history.append(record.copy()),
    )

    alert_evaluator._write_clip_alert(
        client,
        {
            "event_type": "clip_created",
            "alert_id": "cam_02_123_density_high",
            "alert_type": "density_high",
            "trigger_ts": "2026-07-05T05:58:18.296374+00:00",
            "clip_duration_sec": 8,
            "clip_s3_key": "clips/cam_02/density.mp4",
            "clip_s3_uri": "s3://bucket/clips/cam_02/density.mp4",
            "source": {
                "camera_id": "cam_02",
                "store_id": "store_001",
            },
        },
    )

    record = client.hashes["alert:item:cam_02_123_density_high"]
    assert record["store_id"] == "store_001"
    assert record["zone"] == "camera"
    assert record["clip_s3_key"] == "clips/cam_02/density.mp4"
    assert record["snapshot_key"] == "snapshots/cam_02/cam_02_123_density_high.jpg"
    assert written_history[0]["alert_id"] == "cam_02_123_density_high"


def test_evaluate_once_routes_queue_alerts_with_camera_store_id(monkeypatch):
    captured: list[tuple[str, str]] = []

    monkeypatch.setattr(
        alert_evaluator,
        "_check_queue_zones",
        lambda client, cam, store_id, overcrowded_threshold, long_wait_ms, cooldown_sec: captured.append((cam, store_id)),
    )

    alert_evaluator._evaluate_once(
        client=object(),
        camera_ids=["cam_01", "cam_02"],
        settings={"alert_queue_overcrowded_threshold": 2, "alert_long_wait_ms": 15000, "alert_cooldown_sec": 60},
        camera_store_ids={"cam_01": "store_001", "cam_02": "store_002"},
    )

    assert captured == [("cam_01", "store_001"), ("cam_02", "store_002")]
