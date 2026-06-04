"""Ultralytics YOLO detector that returns ``supervision.Detections``."""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
from ultralytics import YOLO

from utils.path_utils import resolve_model_path

logger = logging.getLogger(__name__)

try:  # Supervision is the canonical Vision data model in the rebuilt pipeline.
    import supervision as sv
except Exception:  # pragma: no cover - exercised only when dependency is absent.
    sv = None  # type: ignore[assignment]


class SupervisionYoloDetector:
    """Runs YOLO on a single frame and normalizes output to ``sv.Detections``."""

    detector_type = "ultralytics_yolo"

    def __init__(
        self,
        model_name: str,
        *,
        conf_thres: float = 0.15,
        class_filter: list[int] | None = None,
        iou: float = 0.70,
        imgsz: int | None = 1280,
        half: bool = True,
        device: Any | None = None,
    ) -> None:
        if sv is None:
            raise RuntimeError(
                "supervision is required for the rebuilt Vision pipeline. "
                "Install the rva-vision dependencies first."
            )

        self.model_name = model_name
        self.model_path = resolve_model_path(model_name)
        self.conf_thres = float(conf_thres)
        self.class_filter = class_filter
        self.iou = float(iou)
        self.imgsz = int(imgsz) if imgsz else None
        self.half = bool(half)
        self.device = self._select_device(device)

        logger.info("Loading YOLO detector: %s", self.model_path)
        self.model = YOLO(self.model_path)
        self.names = getattr(self.model, "names", {}) or {}
        logger.info(
            "YOLO detector ready: device=%s conf=%.2f imgsz=%s classes=%s",
            self.device,
            self.conf_thres,
            self.imgsz,
            self.class_filter,
        )

    def predict(self, frame: np.ndarray):
        kwargs: dict[str, Any] = {
            "source": frame,
            "classes": self.class_filter,
            "conf": self.conf_thres,
            "iou": self.iou,
            "device": self.device,
            "verbose": False,
        }
        if self.imgsz:
            kwargs["imgsz"] = self.imgsz
        if self.half and self.device != "cpu":
            kwargs["half"] = True

        results = self.model.predict(**kwargs)
        if not results:
            return sv.Detections.empty()
        return sv.Detections.from_ultralytics(results[0])

    @staticmethod
    def _select_device(configured: Any | None) -> Any:
        if configured not in (None, ""):
            return configured

        force_gpu = os.getenv("FORCE_GPU", "0") == "1"
        try:
            import torch

            if force_gpu:
                if not torch.cuda.is_available():
                    raise RuntimeError("FORCE_GPU=1 but CUDA is not available")
                return 0
            return 0 if torch.cuda.is_available() else "cpu"
        except ImportError:
            if force_gpu:
                raise RuntimeError("FORCE_GPU=1 but torch is not installed")
            return "cpu"
