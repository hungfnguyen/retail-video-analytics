"""Publish latest annotated frames for the live dashboard media gateway."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveFramePublisherConfig:
    output_dir: Path
    fps: float = 10.0
    jpeg_quality: int = 80


class LiveFramePublisher:
    """Writes the latest annotated frame per camera as an atomic JPEG file.

    This is the MVP media-plane bridge for Option 1. Vision owns video decode,
    detection, tracking, and overlay rendering; FastAPI only serves the latest
    JPEG as an MJPEG stream. Redis/Flink stay out of the video byte path.
    """

    def __init__(self, camera_id: str, config: LiveFramePublisherConfig) -> None:
        self.camera_id = camera_id
        self.output_dir = config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frame_path = self.output_dir / f"{camera_id}.jpg"
        self.metadata_path = self.output_dir / f"{camera_id}.json"
        self.min_interval_sec = 1.0 / max(config.fps, 0.1)
        self.jpeg_quality = max(1, min(int(config.jpeg_quality), 100))
        self._last_publish_monotonic = 0.0

    def publish(
        self,
        frame: np.ndarray,
        *,
        frame_index: int,
        capture_ts: datetime,
        detections_count: int,
        extra_metrics: dict[str, Any] | None = None,
    ) -> bool:
        now = time.monotonic()
        if now - self._last_publish_monotonic < self.min_interval_sec:
            return False

        encode_started = time.perf_counter()
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        encode_ms = max(0, int((time.perf_counter() - encode_started) * 1000))
        if not ok:
            logger.warning("Could not encode live frame for camera %s", self.camera_id)
            return False

        publish_interval_ms = (
            max(0, int((now - self._last_publish_monotonic) * 1000))
            if self._last_publish_monotonic > 0
            else 0
        )
        publish_fps = (
            round(1000.0 / publish_interval_ms, 2)
            if publish_interval_ms > 0
            else 0.0
        )
        payload = encoded.tobytes()
        self._atomic_write_bytes(self.frame_path, payload)
        metadata = {
            "camera_id": self.camera_id,
            "frame_index": frame_index,
            "capture_ts": capture_ts.isoformat(),
            "detections_count": detections_count,
            "updated_at_epoch_ms": int(time.time() * 1000),
            "publish_fps": publish_fps,
            "jpeg_size_bytes": len(payload),
            "encode_ms": encode_ms,
            "publish_interval_ms": publish_interval_ms,
        }
        if extra_metrics:
            metadata.update(extra_metrics)
        self._atomic_write_text(
            self.metadata_path,
            json.dumps(metadata, separators=(",", ":")),
        )
        self._last_publish_monotonic = now
        return True

    @staticmethod
    def _atomic_write_bytes(path: Path, payload: bytes) -> None:
        tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}")
        with open(tmp_path, "wb") as f:
            f.write(payload)
        os.replace(tmp_path, path)

    @staticmethod
    def _atomic_write_text(path: Path, payload: str) -> None:
        tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, path)


def create_live_frame_publisher(
    camera_id: str,
    global_cfg: dict[str, Any],
) -> LiveFramePublisher | None:
    if not global_cfg.get("live_media_enabled", True):
        return None

    output_dir = Path(global_cfg.get("live_media_dir", "runtime/live_frames"))
    publisher = LiveFramePublisher(
        camera_id=camera_id,
        config=LiveFramePublisherConfig(
            output_dir=output_dir,
            fps=float(global_cfg.get("live_media_fps", 10.0)),
            jpeg_quality=int(global_cfg.get("live_media_jpeg_quality", 80)),
        ),
    )
    logger.info(
        "Live media enabled: camera=%s dir=%s fps=%.1f quality=%d",
        camera_id,
        publisher.output_dir,
        1.0 / publisher.min_interval_sec,
        publisher.jpeg_quality,
    )
    return publisher
