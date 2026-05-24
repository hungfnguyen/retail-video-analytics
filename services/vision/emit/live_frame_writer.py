from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import cv2

logger = logging.getLogger(__name__)


class LiveFrameWriter:
    def __init__(self, output_dir: str | Path, jpeg_quality: int = 80, max_fps: float = 8.0):
        self.output_dir = Path(output_dir)
        self.jpeg_quality = int(jpeg_quality)
        self.min_interval_sec = 1.0 / max(1.0, float(max_fps))
        self._last_write_by_camera: dict[str, float] = {}
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, camera_id: str, frame: Any) -> None:
        now = time.monotonic()
        if now - self._last_write_by_camera.get(camera_id, 0.0) < self.min_interval_sec:
            return

        output_path = self.output_dir / f"{camera_id}.jpg"
        temp_path = self.output_dir / f"{camera_id}.{time.time_ns()}.tmp.jpg"

        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            logger.warning("Cannot encode live frame for camera %s", camera_id)
            return

        try:
            temp_path.write_bytes(buffer.tobytes())
            os.replace(temp_path, output_path)
            self._last_write_by_camera[camera_id] = now
        except OSError:
            logger.warning("Cannot update live frame for camera %s", camera_id, exc_info=True)
            temp_path.unlink(missing_ok=True)
