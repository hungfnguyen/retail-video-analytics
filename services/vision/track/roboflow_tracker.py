"""Roboflow Trackers adapters for ``supervision.Detections``."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import supervision as sv
except Exception:  # pragma: no cover
    sv = None  # type: ignore[assignment]


class NoOpDetectionsTracker:
    tracker_type = "none"

    def update(self, detections):
        return detections

    def reset(self) -> None:
        return None


class RoboflowByteTrackAdapter:
    """Thin adapter around ``trackers.ByteTrackTracker``.

    Direct package usage is isolated here so future API changes only affect one
    module. The worker sees a stable ``update(sv.Detections)`` interface.
    """

    tracker_type = "roboflow_bytetrack"

    def __init__(self, **kwargs: Any) -> None:
        try:
            from trackers import ByteTrackTracker
        except Exception as exc:  # pragma: no cover - dependency/environment only.
            raise RuntimeError(
                "trackers.ByteTrackTracker is required for tracker_type="
                "roboflow_bytetrack. Install the rva-vision dependencies."
            ) from exc

        self._constructor_kwargs = self._clean_kwargs(kwargs)
        try:
            self.tracker = ByteTrackTracker(**self._constructor_kwargs)
        except TypeError:
            # Keep the pipeline runnable if the installed trackers build has a
            # narrower constructor than the docs version used for the plan.
            logger.warning(
                "ByteTrackTracker rejected kwargs %s; retrying with defaults",
                sorted(self._constructor_kwargs),
                exc_info=True,
            )
            self._constructor_kwargs = {}
            self.tracker = ByteTrackTracker()

    def update(self, detections):
        return self.tracker.update(detections)

    def reset(self) -> None:
        reset = getattr(self.tracker, "reset", None)
        if callable(reset):
            reset()

    @staticmethod
    def _clean_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "track_activation_threshold",
            "lost_track_buffer",
            "minimum_consecutive_frames",
            "frame_rate",
            "minimum_iou_threshold",
            "high_conf_det_threshold",
        }
        clean: dict[str, Any] = {}
        for key in allowed:
            value = kwargs.get(key)
            if value is not None:
                clean[key] = value
        return clean


class DetectionsSmootherAdapter:
    def __init__(self, *, enabled: bool = True, length: int = 5) -> None:
        self.enabled = bool(enabled)
        self.length = max(1, int(length))
        self.smoother = None
        if self.enabled and sv is not None:
            self.smoother = sv.DetectionsSmoother(length=self.length)

    def update(self, detections):
        if not self.smoother:
            return detections
        try:
            return self.smoother.update_with_detections(detections)
        except Exception:
            logger.warning("DetectionsSmoother failed; returning unsmoothed detections", exc_info=True)
            return detections


def create_supervision_tracker(tracker_name: str, global_cfg: dict[str, Any]):
    tracker = (tracker_name or "roboflow_bytetrack").lower().strip()
    if tracker in {"roboflow_bytetrack", "bytetrack", "byte_track"}:
        return RoboflowByteTrackAdapter(
            track_activation_threshold=_float(global_cfg, "track_activation_threshold", 0.20),
            lost_track_buffer=_int(global_cfg, "lost_track_buffer", 60),
            minimum_consecutive_frames=_int(global_cfg, "minimum_consecutive_frames", 2),
            frame_rate=_int(global_cfg, "tracker_frame_rate", None),
            minimum_iou_threshold=_float(global_cfg, "minimum_iou_threshold", None),
            high_conf_det_threshold=_float(global_cfg, "high_conf_det_threshold", None),
        )
    if tracker in {"none", "noop"}:
        return NoOpDetectionsTracker()
    logger.warning("Unsupported rebuilt tracker_type=%s; falling back to ByteTrack", tracker_name)
    return RoboflowByteTrackAdapter(
        track_activation_threshold=_float(global_cfg, "track_activation_threshold", 0.20),
        lost_track_buffer=_int(global_cfg, "lost_track_buffer", 60),
        minimum_consecutive_frames=_int(global_cfg, "minimum_consecutive_frames", 2),
    )


def create_detections_smoother(global_cfg: dict[str, Any]) -> DetectionsSmootherAdapter:
    return DetectionsSmootherAdapter(
        enabled=bool(global_cfg.get("track_smoothing_enabled", True)),
        length=int(global_cfg.get("track_smoothing_length", 5)),
    )


def _int(cfg: dict[str, Any], key: str, default: int | None) -> int | None:
    value = cfg.get(key, default)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(cfg: dict[str, Any], key: str, default: float | None) -> float | None:
    value = cfg.get(key, default)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
