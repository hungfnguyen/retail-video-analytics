from __future__ import annotations

import sys
import threading
from pathlib import Path
from queue import Queue

import numpy as np

VISION_PATH = Path(__file__).resolve().parents[2] / "services" / "vision"
if str(VISION_PATH) not in sys.path:
    sys.path.insert(0, str(VISION_PATH))

from config.settings import load_cameras_config  # noqa: E402
from features.detections import add_global_track_ids, track_to_detection  # noqa: E402
from inference.shared_yolo import SharedInferenceClient  # noqa: E402
from zones.zone_manager import RetailZoneRuntime, ZoneSpec  # noqa: E402


def test_track_to_detection_adds_global_id_anchor_zone_and_queue():
    track = {
        "id": 7,
        "raw_track_id": 99,
        "global_track_id": "cam_01_g_000007",
        "bbox": [100.0, 120.0, 220.0, 420.0],
        "cls": 0,
        "label": "person",
        "conf": 0.86,
        "queue_wait_ms": 68_000,
        "queue_wait_seconds": 68,
    }
    zones = [
        {
            "zone_id": "checkout_queue_01",
            "zone_name": "Checkout Queue 01",
            "zone_type": "queue",
            "is_primary": True,
        }
    ]

    detection = track_to_detection(
        frame_index=12,
        object_index=0,
        obj=track,
        width=1280,
        height=720,
        zones=zones,
    )

    assert detection["track_id"] == 7
    assert detection["raw_track_id"] == 99
    assert detection["global_track_id"] == "cam_01_g_000007"
    assert detection["anchor"]["type"] == "bottom_center"
    assert detection["anchor"]["x"] == 160
    assert detection["anchor"]["y"] == 420
    assert detection["queue"]["in_queue"] is True
    assert detection["queue"]["queue_zone_id"] == "checkout_queue_01"
    assert detection["queue"]["wait_ms"] == 68_000
    assert detection["queue"]["wait_seconds"] == 68


def test_add_global_track_ids_uses_stable_integer_id():
    tracks = [{"id": 42, "detector_ids": [12, 31], "bbox": [0, 0, 10, 10]}]

    add_global_track_ids(tracks, "cam_01")

    assert tracks[0]["global_track_id"] == "cam_01_g_000042"
    assert tracks[0]["raw_track_id"] == 31


def test_zone_runtime_assigns_bottom_center_to_polygon():
    runtime = RetailZoneRuntime(
        version="test-zones",
        zones=[
            ZoneSpec(
                zone_id="checkout_queue_01",
                zone_name="Checkout Queue 01",
                zone_type="queue",
                priority=100,
                polygon_norm=[[0.4, 0.4], [0.8, 0.4], [0.8, 0.9], [0.4, 0.9]],
            )
        ],
        lines=[],
    )
    tracks = [
        {
            "id": 1,
            "global_track_id": "cam_01_g_000001",
            "bbox": [500.0, 200.0, 650.0, 600.0],
            "cls": 0,
            "conf": 0.9,
        }
    ]

    assignments, counts = runtime.assign(tracks, width=1280, height=720)

    assert assignments[0][0]["zone_id"] == "checkout_queue_01"
    assert assignments[0][0]["is_primary"] is True
    assert counts[0]["count"] == 1
    assert counts[0]["global_track_ids"] == ["cam_01_g_000001"]


def test_load_cameras_config_supports_shared_inference(tmp_path):
    config_path = tmp_path / "cameras.yaml"
    config_path.write_text(
        """
cameras:
  - camera_id: cam_01
    store_id: store_001
    source_type: video_file
    source_uri: data/videos/video1.mp4
    enabled: true
settings:
  model_name: yolo11l.pt
  tracker_type: roboflow_bytetrack
  conf_thres: 0.15
  shared_inference_enabled: true
  shared_inference_queue_size: 8
  shared_inference_timeout_sec: 12
"""
    )

    cfg = load_cameras_config(str(config_path))

    assert cfg["shared_inference_enabled"] is True
    assert cfg["shared_inference_queue_size"] == 8
    assert cfg["shared_inference_timeout_sec"] == 12.0


def test_shared_inference_client_matches_response_by_request_id():
    request_queue = Queue()
    response_queue = Queue()
    client = SharedInferenceClient(
        camera_id="cam_01",
        request_queue=request_queue,
        response_queue=response_queue,
        timeout_sec=1.0,
    )

    def serve_once():
        request = request_queue.get(timeout=1.0)
        response_queue.put({"request_id": "stale", "detections": "wrong"})
        response_queue.put(
            {
                "request_id": request["request_id"],
                "detections": "detections",
                "names": {0: "person"},
                "error": None,
            }
        )

    thread = threading.Thread(target=serve_once)
    thread.start()

    result = client.predict(np.zeros((4, 4, 3), dtype=np.uint8))
    thread.join(timeout=1.0)

    assert result == "detections"
    assert client.names == {0: "person"}
