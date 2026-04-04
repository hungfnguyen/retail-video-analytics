"""Shared data models for the vision pipeline."""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np


@dataclass
class Detection:
    """Single object detection from YOLO11."""

    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 (pixels)
    confidence: float
    class_id: int
    class_name: str

    @property
    def centroid(self) -> tuple[int, int]:
        """Center point of bounding box."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def area(self) -> int:
        """Bounding box area in pixels."""
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1) * (y2 - y1)


@dataclass
class TrackedObject:
    """Detected person with persistent track ID across frames."""

    track_id: int
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 (pixels)
    confidence: float
    class_name: str

    # Track lifecycle state
    is_confirmed: bool = False          # True after track_buffer frames
    frames_since_seen: int = 0          # Frames elapsed since last match
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    # Optional ReID appearance feature vector
    feature: np.ndarray | None = field(default=None, repr=False)

    @property
    def centroid(self) -> tuple[int, int]:
        """Center point of bounding box."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)


@dataclass
class FrameResult:
    """Complete processing result for a single frame."""

    camera_id: str
    store_id: str
    frame_index: int
    capture_ts: datetime
    frame: np.ndarray = field(repr=False)
    tracks: list[TrackedObject] = field(default_factory=list)

    @property
    def person_count(self) -> int:
        """Number of confirmed tracked persons in this frame."""
        return sum(1 for t in self.tracks if t.is_confirmed)
