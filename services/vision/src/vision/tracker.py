"""BoTSORT tracker wrapper.

Thin adapter over the existing vision.track.yolo_tracker_botsort.YoloBoTSORTTracker,
converting its output dicts into typed TrackedObject instances.

Note: BoTSORT tracking state (track IDs, Kalman filters) is **per-process**.
Each CameraWorker subprocess gets its own Tracker instance with independent state.
"""

import logging
from datetime import datetime, timezone

import numpy as np

from vision.models import Detection, TrackedObject
from vision.track.yolo_tracker_base import YoloTrackerBase

logger = logging.getLogger(__name__)


class Tracker:
    """BoTSORT multi-object tracker.

    Maintains persistent track IDs across frames for detected persons.
    One instance per camera — do not share between processes.

    Args:
        camera_id: Used for logging context only.
        model_path: YOLO11 model path (BoTSORT runs detection internally).
        conf_threshold: Minimum confidence for tracking.
        track_buffer: Number of frames to keep a lost track alive.
    """

    def __init__(
        self,
        camera_id: str,
        model_path: str = "data/models/yolo11n.pt",
        conf_threshold: float = 0.5,
        track_buffer: int = 30,
    ) -> None:
        # TODO: instantiate YoloBoTSORTTracker from vision.track.yolo_tracker_botsort
        raise NotImplementedError

    def update(
        self,
        detections: list[Detection],
        frame: np.ndarray,
        timestamp: datetime | None = None,
    ) -> list[TrackedObject]:
        """Associate detections with existing tracks and return tracked objects.

        Args:
            detections: Person detections from :class:`Detector`.
            frame: Current BGR frame (used for appearance feature extraction).
            timestamp: Frame capture time; defaults to utcnow().

        Returns:
            List of :class:`TrackedObject` with assigned track IDs.
            Only confirmed tracks (is_confirmed=True) are suitable for
            downstream publishing.
        """
        # TODO:
        # 1. Convert Detection list to the format expected by YoloTrackerBase
        # 2. Run tracker update step
        # 3. Convert output dicts to TrackedObject instances
        # 4. Set is_confirmed, first_seen, last_seen on each object
        raise NotImplementedError

    def reset(self) -> None:
        """Reset all tracking state (track IDs, Kalman filters).

        Call this on camera reconnect to avoid stale tracks.
        """
        # TODO: re-instantiate the underlying tracker
        raise NotImplementedError
