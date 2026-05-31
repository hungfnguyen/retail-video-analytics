from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from rva_api.api.v1 import live, system


class FakeRedis:
    def __init__(self):
        frame = {
            "camera_id": "cam_01",
            "frame_index": 10,
            "capture_ts": datetime.now(timezone.utc).isoformat(),
            "detections": [{"track_id": 1}, {"track_id": 2}],
        }
        self.values = {
            "live:frame:cam_01": json.dumps(frame),
            "stats:count:cam_01": "2",
        }
        self.track_keys = ["track:active:cam_01:1", "track:active:cam_01:2"]

    def get(self, key):
        return self.values.get(key)

    def scan_iter(self, match):
        yield from [key for key in self.track_keys if key.startswith(match.rstrip("*"))]


def test_system_dashboard_maps_live_health_and_runtime_signals(monkeypatch):
    monkeypatch.setattr(system, "_get_redis_client", lambda: FakeRedis())
    monkeypatch.setattr(live, "_tcp_health", lambda raw: ("ok", 1))
    monkeypatch.setattr(system, "_recent_logs", lambda: [])
    monkeypatch.setattr(
        system,
        "_read_media_metadata",
        lambda camera_id: {
            "camera_id": camera_id,
            "updated_at_epoch_ms": int(time.time() * 1000),
            "processing_fps": 3.5,
            "reader_queue_size": 4,
        },
    )

    data = system.get_system_dashboard("cam_01")

    assert {service.service for service in data.pipeline_health} == {
        "pulsar",
        "flink",
        "redis",
        "s3",
        "trino",
        "fastapi",
    }
    assert data.throughput[0].events == 2
    assert data.throughput[0].frames == 3.5
    assert data.lag[0].backlog == 4
    assert len(data.containers) == 6
    assert data.flow[0].name == "Vision Edge"


def test_system_dashboard_handles_missing_runtime_sources(monkeypatch):
    monkeypatch.setattr(system, "_get_redis_client", lambda: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(live, "_tcp_health", lambda raw: ("down", 0))
    monkeypatch.setattr(system, "_recent_logs", lambda: [])
    monkeypatch.setattr(system, "_read_media_metadata", lambda camera_id: {})

    data = system.get_system_dashboard("cam_01")

    assert data.throughput == []
    assert data.lag == []
    assert data.logs == []
    redis_health = next(
        service for service in data.pipeline_health if service.service == "redis"
    )
    assert redis_health.status == "down"
