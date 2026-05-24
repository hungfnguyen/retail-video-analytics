from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "vision"
    / "media"
    / "live_frame_publisher.py"
)
spec = importlib.util.spec_from_file_location("live_frame_publisher", MODULE_PATH)
assert spec is not None and spec.loader is not None
live_frame_publisher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = live_frame_publisher
spec.loader.exec_module(live_frame_publisher)

LiveFramePublisher = live_frame_publisher.LiveFramePublisher
LiveFramePublisherConfig = live_frame_publisher.LiveFramePublisherConfig


def test_live_frame_publisher_writes_observability_metadata(tmp_path):
    publisher = LiveFramePublisher(
        "cam_01",
        LiveFramePublisherConfig(output_dir=tmp_path, fps=1000.0, jpeg_quality=70),
    )
    frame = np.zeros((24, 32, 3), dtype=np.uint8)

    assert publisher.publish(
        frame,
        frame_index=1,
        capture_ts=datetime.now(timezone.utc),
        detections_count=2,
    )
    assert publisher.publish(
        frame,
        frame_index=2,
        capture_ts=datetime.now(timezone.utc),
        detections_count=3,
        extra_metrics={
            "processing_fps": 2.5,
            "inference_ms": 390,
            "draw_ms": 2,
            "reader_drop_count": 10,
        },
    )

    metadata = json.loads((tmp_path / "cam_01.json").read_text(encoding="utf-8"))

    assert (tmp_path / "cam_01.jpg").exists()
    assert metadata["camera_id"] == "cam_01"
    assert metadata["frame_index"] == 2
    assert metadata["detections_count"] == 3
    assert metadata["jpeg_size_bytes"] > 0
    assert metadata["encode_ms"] >= 0
    assert metadata["publish_interval_ms"] >= 0
    assert metadata["publish_fps"] >= 0
    assert metadata["processing_fps"] == 2.5
    assert metadata["inference_ms"] == 390
    assert metadata["draw_ms"] == 2
    assert metadata["reader_drop_count"] == 10
