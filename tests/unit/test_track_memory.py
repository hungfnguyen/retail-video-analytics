from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "vision"
    / "track"
    / "track_memory.py"
)
spec = importlib.util.spec_from_file_location("track_memory", MODULE_PATH)
assert spec is not None and spec.loader is not None
track_memory = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = track_memory
spec.loader.exec_module(track_memory)

TrackMemory = track_memory.TrackMemory
TrackMemoryConfig = track_memory.TrackMemoryConfig


def _obj(track_id: int, bbox: list[float] | None = None, conf: float = 0.8):
    return {
        "id": track_id,
        "bbox": bbox or [10.0, 20.0, 50.0, 100.0],
        "cls": 0,
        "label": "person",
        "conf": conf,
    }


def test_track_memory_keeps_predicted_track_through_short_gap():
    memory = TrackMemory(
        TrackMemoryConfig(
            lost_ttl_frames=3,
            lost_ttl_ms=1_000,
            min_predicted_conf=0.1,
        )
    )

    first = memory.update([_obj(7)], frame_index=1, timestamp_ms=0)
    second = memory.update([], frame_index=2, timestamp_ms=40)

    assert first[0]["id"] == 7
    assert first[0]["track_state"] == "matched"
    assert second[0]["id"] == 7
    assert second[0]["track_state"] == "predicted"
    assert second[0]["missed_frames"] == 1
    assert memory.summary(second)["stable_tracks_count"] == 1
    assert memory.summary(second)["predicted_tracks_count"] == 1


def test_track_memory_removes_track_after_gap_ttl():
    memory = TrackMemory(
        TrackMemoryConfig(
            lost_ttl_frames=1,
            lost_ttl_ms=1_000,
            min_predicted_conf=0.1,
        )
    )

    memory.update([_obj(7)], frame_index=1, timestamp_ms=0)
    predicted = memory.update([], frame_index=2, timestamp_ms=40)
    removed = memory.update([], frame_index=3, timestamp_ms=80)

    assert predicted[0]["track_state"] == "predicted"
    assert removed == []


def test_track_memory_stitches_new_detector_id_to_lost_track():
    memory = TrackMemory(
        TrackMemoryConfig(
            lost_ttl_frames=5,
            lost_ttl_ms=1_000,
            reid_iou_threshold=0.1,
            reid_center_distance_px=80.0,
        )
    )

    memory.update([_obj(7, [10.0, 20.0, 50.0, 100.0])], frame_index=1, timestamp_ms=0)
    memory.update([], frame_index=2, timestamp_ms=40)
    stitched = memory.update(
        [_obj(99, [12.0, 22.0, 52.0, 102.0])],
        frame_index=3,
        timestamp_ms=80,
    )

    assert stitched[0]["id"] == 7
    assert stitched[0]["raw_track_id"] == 99
    assert stitched[0]["track_state"] == "matched"
    assert stitched[0]["detector_ids"] == [7, 99]
    assert memory.summary(stitched)["id_switch_suspect_count"] == 1


def test_track_memory_disabled_marks_raw_detections_as_matched():
    memory = TrackMemory(TrackMemoryConfig(enabled=False))

    tracks = memory.update([_obj(5)], frame_index=1, timestamp_ms=0)

    assert tracks[0]["id"] == 5
    assert tracks[0]["track_state"] == "matched"
    assert tracks[0]["measurement_source"] == "full_body"
