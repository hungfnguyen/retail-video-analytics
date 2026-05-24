from __future__ import annotations

import json
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
            "stats:fps:cam_01": "24.8",
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

    data = live.get_live_dashboard("cam_01")

    assert data.selected_camera_id == "cam_01"
    assert data.stats.current_count == 1
    assert data.stats.active_tracks == 1
    assert data.stats.fps == 24.8
    assert data.frame.frame_id == 1500
    assert data.frame.fps == 24.8
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
