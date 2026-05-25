from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from rva_api.api.v1 import live


class FakeRedis:
    def __init__(self):
        frame = {
            "schema_version": "1.0",
            "event_id": "evt_001",
            "camera_id": "cam_01",
            "store_id": "store_001",
            "frame_index": 1500,
            "capture_ts": datetime.now(timezone.utc).isoformat(),
            "image_size": {"width": 1920, "height": 1080},
            "detections": [
                {
                    "track_id": 42,
                    "label": "person",
                    "confidence": 0.85,
                    "bbox_norm": {"x": 0.5, "y": 0.5, "w": 0.1, "h": 0.5},
                    "centroid_norm": {"x": 0.55, "y": 0.75},
                    "grid_x": 35,
                    "grid_y": 36,
                }
            ],
        }
        self.values = {
            "live:frame:cam_01": json.dumps(frame),
            "stats:count:cam_01": "1",
        }
        self.track_keys = ["track:active:cam_01:42"]
        self.heatmap = [("35,36", 4.0), ("10,12", 2.0)]

    def ping(self):
        return True

    def get(self, key):
        return self.values.get(key)

    def scan_iter(self, match):
        yield from [key for key in self.track_keys if key.startswith(match.rstrip("*"))]

    def zrevrange(self, key, start, end, withscores=False):
        assert key == "heatmap:live:cam_01"
        members = self.heatmap[start : end + 1]
        return members if withscores else [member for member, _ in members]


def test_live_dashboard_maps_redis_state(monkeypatch):
    monkeypatch.setattr(live, "_get_redis_client", lambda: FakeRedis())
    monkeypatch.setattr(
        live,
        "_load_camera_config",
        lambda: [
            {
                "camera_id": "cam_01",
                "store_id": "store_001",
                "name": "Entrance",
                "source_type": "video_file",
                "enabled": True,
            }
        ],
    )
    monkeypatch.setattr(
        live,
        "_read_media_metadata",
        lambda camera_id: {
            "camera_id": camera_id,
            "updated_at_epoch_ms": int(time.time() * 1000),
            "publish_fps": 12.5,
            "processing_fps": 2.4,
            "inference_ms": 380,
            "postprocess_ms": 4,
            "draw_ms": 3,
            "jpeg_size_bytes": 123456,
            "encode_ms": 6,
            "publish_interval_ms": 80,
            "reader_queue_size": 1,
            "reader_drop_count": 7,
        },
    )

    data = live.get_live_dashboard("cam_01")

    assert data.selected_camera_id == "cam_01"
    assert data.stats.current_count == 1
    assert data.stats.count_source == "redis"
    assert data.stats.active_tracks == 1
    assert data.frame.frame_id == 1500
    assert data.frame.image_url == "/media/live/cam_01/stream"
    assert data.frame.media_fps == 12.5
    assert data.frame.media_latency_ms < 1_000
    assert data.frame.media_status == "online"
    assert data.frame.metadata_latency_ms < 1_000
    assert data.frame.metadata_status == "fresh"
    assert data.stats.media_fps == 12.5
    assert data.stats.metadata_latency_ms < 1_000
    assert data.stats.metadata_status == "fresh"
    assert data.frame.processing_fps == 2.4
    assert data.frame.inference_ms == 380
    assert data.frame.postprocess_ms == 4
    assert data.frame.draw_ms == 3
    assert data.frame.encode_ms == 6
    assert data.frame.jpeg_size_bytes == 123456
    assert data.frame.reader_queue_size == 1
    assert data.frame.reader_drop_count == 7
    assert data.frame.detections[0].track_id == 42
    assert data.frame.detections[0].bbox_norm.w == 0.1
    assert data.frame.heatmap_points[0].intensity == 1.0
    assert len(data.zone_heatmap) == 42
    assert max(cell.value for cell in data.zone_heatmap) == 100
    assert data.pipeline_health[0].service == "redis"


def test_get_redis_client_raises_503_when_unavailable(monkeypatch):
    monkeypatch.setattr(live, "_redis_client", None)
    monkeypatch.setattr(live, "create_redis_client", lambda config: None)

    with pytest.raises(HTTPException) as exc_info:
        live._get_redis_client()

    assert exc_info.value.status_code == 503


def test_read_media_metadata_from_configured_dir(monkeypatch, tmp_path):
    metadata_path = tmp_path / "cam_01.json"
    metadata_path.write_text(
        json.dumps({"updated_at_epoch_ms": int(time.time() * 1000), "publish_fps": 9.5}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RVA_LIVE_MEDIA_DIR", str(tmp_path))

    metadata = live._read_media_metadata("cam_01")

    assert metadata["publish_fps"] == 9.5
    assert live._media_status(metadata, live._media_latency_ms(metadata)) == "online"


def test_media_metadata_missing_is_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("RVA_LIVE_MEDIA_DIR", str(tmp_path))

    metadata = live._read_media_metadata("cam_01")

    assert metadata == {}
    assert live._media_latency_ms(metadata) is None
    assert live._media_status(metadata, None) == "missing"


def test_live_dashboard_falls_back_to_live_frame_count(monkeypatch):
    fake_redis = FakeRedis()
    fake_redis.values.pop("stats:count:cam_01")
    monkeypatch.setattr(live, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(live, "_load_camera_config", lambda: [])
    monkeypatch.setattr(
        live,
        "_read_media_metadata",
        lambda camera_id: {
            "camera_id": camera_id,
            "updated_at_epoch_ms": int(time.time() * 1000),
            "publish_fps": 8.0,
        },
    )

    data = live.get_live_dashboard("cam_01")

    assert data.stats.current_count == 1
    assert data.stats.count_source == "live_frame_fallback"
    assert data.stats.status == "stable"
    assert data.traffic_summary.current_total == 1


def test_live_dashboard_prefers_camera_realtime_count_when_media_is_online(monkeypatch):
    fake_redis = FakeRedis()
    fake_redis.values["stats:count:cam_01"] = "99"
    media_capture_ts = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(live, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(live, "_load_camera_config", lambda: [])
    monkeypatch.setattr(
        live,
        "_read_media_metadata",
        lambda camera_id: {
            "camera_id": camera_id,
            "frame_index": 1600,
            "capture_ts": media_capture_ts,
            "updated_at_epoch_ms": int(time.time() * 1000),
            "publish_fps": 12.0,
            "tracked_objects_count": 3,
            "detections_count": 4,
        },
    )

    data = live.get_live_dashboard("cam_01")

    assert data.stats.current_count == 3
    assert data.stats.count_source == "camera_realtime"
    assert data.stats.updated_at == media_capture_ts
    assert data.frame.frame_id == 1600
    assert data.frame.capture_ts == media_capture_ts
    assert data.traffic_summary.current_total == 3


def test_live_dashboard_marks_count_missing_when_frame_is_stale(monkeypatch):
    fake_redis = FakeRedis()
    fake_redis.values.pop("stats:count:cam_01")
    frame = json.loads(fake_redis.values["live:frame:cam_01"])
    frame["capture_ts"] = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    fake_redis.values["live:frame:cam_01"] = json.dumps(frame)
    monkeypatch.setattr(live, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(live, "_load_camera_config", lambda: [])
    monkeypatch.setattr(
        live,
        "_read_media_metadata",
        lambda camera_id: {
            "camera_id": camera_id,
            "updated_at_epoch_ms": int(time.time() * 1000),
            "publish_fps": 8.0,
        },
    )

    data = live.get_live_dashboard("cam_01")

    assert data.stats.current_count == 0
    assert data.stats.count_source == "missing"
    assert data.stats.metadata_status == "stale"
    assert data.stats.status == "warning"
    assert data.pipeline_health[1].status == "warning"
