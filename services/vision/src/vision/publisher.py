"""Detection publisher — Pulsar metadata + GCS frame uploads.

Per-frame: publishes detection JSON to Apache Pulsar.
Per-second: uploads JPEG keyframe to Google Cloud Storage.

Both operations are non-blocking:
- Pulsar: existing PulsarEmitter._send_with_retry handles async internally.
- GCS:    uploads offloaded to a ThreadPoolExecutor (max_workers=2).

GCS path pattern:
    gs://{bucket}/frames/{YYYY-MM-DD}/{camera_id}/{HH-MM-SS}_{frame_idx:06d}.jpg
"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

import cv2
import numpy as np

from vision.emit.pulsar_emitter import PulsarEmitter
from vision.models import TrackedObject

logger = logging.getLogger(__name__)


@dataclass
class PublishConfig:
    """Publisher configuration (one per CameraWorker)."""

    camera_id: str
    store_id: str
    pulsar_service_url: str
    pulsar_topic: str
    gcs_bucket: str
    gcs_upload_interval: float = 1.0   # seconds between GCS frame uploads
    gcs_jpeg_quality: int = 80


class DetectionPublisher:
    """Publish tracking results to Pulsar and sampled frames to GCS.

    Lifecycle::

        publisher = DetectionPublisher(config)
        publisher.publish(tracks, frame, frame_index, timestamp)
        ...
        publisher.close()  # flush Pulsar, shutdown executor
    """

    def __init__(self, config: PublishConfig) -> None:
        self.config = config
        self._pipeline_run_id = uuid.uuid4().hex
        self._last_gcs_upload_ts: float = 0.0
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gcs-upload")

        # TODO: initialise PulsarEmitter (from vision.emit.pulsar_emitter)
        # TODO: initialise google.cloud.storage.Client and bucket reference
        self._pulsar: PulsarEmitter | None = None
        raise NotImplementedError

    # ── Public API ──────────────────────────────────────────────────────────

    def publish(
        self,
        tracks: list[TrackedObject],
        frame: np.ndarray,
        frame_index: int,
        timestamp: datetime,
    ) -> None:
        """Publish one frame's tracking results.

        - Always sends detection metadata to Pulsar.
        - Uploads frame to GCS if gcs_upload_interval seconds have elapsed.

        Args:
            tracks: Tracked persons from :class:`Tracker`.
            frame: BGR frame (for GCS upload, not sent to Pulsar).
            frame_index: Monotonically increasing frame counter.
            timestamp: Frame capture time (UTC).
        """
        # TODO: build message dict, call _publish_to_pulsar
        # TODO: check elapsed since _last_gcs_upload_ts, submit _upload_to_gcs to executor
        raise NotImplementedError

    def close(self) -> None:
        """Flush pending messages and cleanly shut down connections."""
        # TODO: executor.shutdown(wait=True)
        # TODO: self._pulsar.close()
        raise NotImplementedError

    # ── Private ─────────────────────────────────────────────────────────────

    def _build_message(
        self,
        tracks: list[TrackedObject],
        frame_index: int,
        timestamp: datetime,
        frame_shape: tuple[int, int],
    ) -> dict:
        """Build the Pulsar message payload dict.

        Schema matches docs/09_CAMERA_PROCESSING_ARCHITECTURE.md §3.4.

        Args:
            frame_shape: (height, width) of the frame.
        """
        # TODO: construct the JSON-serialisable dict with:
        #   pipeline_run_id, camera_id, store_id, frame_index, capture_ts,
        #   image_size, detections (from tracks)
        raise NotImplementedError

    def _publish_to_pulsar(self, message: dict, frame_index: int) -> None:
        """Serialize and send message to Pulsar via existing PulsarEmitter.

        Delegates retry logic to PulsarEmitter._send_with_retry.
        """
        # TODO: call self._pulsar.emit_frame(pipeline_run_id=..., source=..., ...)
        raise NotImplementedError

    def _upload_to_gcs(self, frame: np.ndarray, timestamp: datetime) -> str | None:
        """Encode frame as JPEG and upload to GCS.

        Called from ThreadPoolExecutor — must be thread-safe.

        Returns:
            GCS URI string ``gs://{bucket}/frames/...`` on success, None on failure.
        """
        # TODO:
        # 1. Build blob path: frames/YYYY-MM-DD/camera_id/HH-MM-SS_{frame_idx:06d}.jpg
        # 2. cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        # 3. blob.upload_from_string(buffer, content_type="image/jpeg")
        # 4. Return f"gs://{bucket}/{blob_path}"
        raise NotImplementedError
