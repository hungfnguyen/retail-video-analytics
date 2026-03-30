"""YOLO11 detector wrapper.

Thin adapter over the existing vision.detect.yolo_detector.YoloDetector,
exposing the Detection dataclass defined in vision.models instead of raw dicts.
"""

import logging

import numpy as np

from vision.detect.yolo_detector import YoloDetector
from vision.models import Detection

logger = logging.getLogger(__name__)

# COCO class ID for "person"
_PERSON_CLASS_ID = 0


class Detector:
    """YOLO11 person detector.

    Wraps :class:`vision.detect.yolo_detector.YoloDetector` and converts
    raw dict detections into typed :class:`vision.models.Detection` objects.

    Args:
        model_path: Path to the YOLO11 weights file (e.g. ``yolo11n.pt``).
        device: Torch device string, e.g. ``"cuda:0"`` or ``"cpu"``.
        conf_threshold: Minimum confidence score to keep a detection.
        iou_threshold: IoU threshold for NMS.
        person_only: If True, filter to class_id == 0 (person) only.
    """

    def __init__(
        self,
        model_path: str = "data/models/yolo11n.pt",
        device: str = "cuda:0",
        conf_threshold: float = 0.5,
        iou_threshold: float = 0.45,
        person_only: bool = True,
    ) -> None:
        # TODO: instantiate YoloDetector, store class_filter ([0] if person_only)
        raise NotImplementedError

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run inference on a BGR frame and return typed detections.

        Args:
            frame: BGR image array of shape (H, W, 3).

        Returns:
            List of :class:`Detection` filtered by confidence and class.
        """
        # TODO:
        # 1. Call self._yolo.predict(frame, class_filter=self._class_filter)
        # 2. Convert each dict result to Detection(bbox=..., confidence=..., ...)
        # 3. Return list
        raise NotImplementedError

    def warmup(self) -> None:
        """Run a blank inference pass to initialise CUDA kernels.

        Call once after construction, before the first real frame.
        """
        # TODO: create a black frame of (640, 640, 3) and call detect()
        raise NotImplementedError
