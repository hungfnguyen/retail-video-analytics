"""Short-term track memory for bridging retail-camera occlusions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


BBox = list[float]


@dataclass(frozen=True)
class TrackMemoryConfig:
    enabled: bool = True
    lost_ttl_ms: int = 1000
    lost_ttl_frames: int = 15
    min_hits: int = 1
    smooth_alpha: float = 0.65
    publish_predicted: bool = True
    count_predicted: bool = True
    predicted_conf_decay: float = 0.85
    min_predicted_conf: float = 0.20
    reid_iou_threshold: float = 0.15
    reid_center_distance_px: float = 120.0


@dataclass
class TrackState:
    canonical_id: int
    detector_ids: set[int] = field(default_factory=set)
    raw_track_id: int | None = None
    bbox: BBox = field(default_factory=list)
    velocity: BBox = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    cls: int = 0
    label: str = "person"
    conf: float = 0.0
    age_frames: int = 0
    hits: int = 0
    missed_frames: int = 0
    last_seen_frame: int = 0
    last_seen_ms: int = 0
    last_update_ms: int = 0
    measurement_source: str = "full_body"
    last_track_state: str = "matched"


class TrackMemory:
    """Maintains stable tracks across short detector gaps.

    BoT-SORT/ByteTrack own frame-level association. This layer owns application
    behavior when a previously visible shopper is briefly occluded.
    """

    def __init__(self, config: TrackMemoryConfig | None = None) -> None:
        self.config = config or TrackMemoryConfig()
        self._tracks: dict[int, TrackState] = {}
        self._detector_to_canonical: dict[int, int] = {}
        self.id_switch_suspect_count = 0

    def update(
        self,
        detections: list[dict[str, Any]],
        *,
        frame_index: int,
        timestamp_ms: int,
    ) -> list[dict[str, Any]]:
        if not self.config.enabled:
            return [self._as_matched_detection(obj, frame_index) for obj in detections]

        matched_ids: set[int] = set()
        for obj in detections:
            detector_id = self._detector_id(obj)
            if detector_id is None:
                continue

            canonical_id = self._detector_to_canonical.get(detector_id)
            if canonical_id is None or canonical_id not in self._tracks:
                matched_lost_id = self._match_lost_track(obj)
                if matched_lost_id is not None:
                    canonical_id = matched_lost_id
                    self.id_switch_suspect_count += 1
                else:
                    canonical_id = detector_id
                self._detector_to_canonical[detector_id] = canonical_id

            state = self._tracks.get(canonical_id)
            if state is None:
                state = TrackState(canonical_id=canonical_id)
                self._tracks[canonical_id] = state

            self._update_matched_state(
                state,
                obj,
                detector_id=detector_id,
                frame_index=frame_index,
                timestamp_ms=timestamp_ms,
            )
            matched_ids.add(canonical_id)

        stable_tracks: list[dict[str, Any]] = []
        dead_ids: list[int] = []
        for canonical_id, state in list(self._tracks.items()):
            if canonical_id not in matched_ids:
                self._predict_missing_state(state, frame_index, timestamp_ms)

            if self._is_dead(state, frame_index, timestamp_ms):
                dead_ids.append(canonical_id)
                continue

            output = self._state_to_output(state)
            if output is not None:
                stable_tracks.append(output)

        for canonical_id in dead_ids:
            self._remove_track(canonical_id)

        stable_tracks.sort(key=lambda item: int(item.get("id", 0)))
        return stable_tracks

    def summary(self, tracks: list[dict[str, Any]]) -> dict[str, int | bool]:
        matched = sum(1 for track in tracks if track.get("track_state") == "matched")
        predicted = sum(1 for track in tracks if track.get("track_state") == "predicted")
        countable = sum(1 for track in tracks if self.is_countable(track))
        return {
            "track_memory_enabled": self.config.enabled,
            "stable_tracks_count": countable,
            "matched_tracks_count": matched,
            "predicted_tracks_count": predicted,
            "id_switch_suspect_count": self.id_switch_suspect_count,
        }

    def is_countable(self, track: dict[str, Any]) -> bool:
        if track.get("track_state") == "matched":
            return True
        return bool(self.config.count_predicted and track.get("track_state") == "predicted")

    def _update_matched_state(
        self,
        state: TrackState,
        obj: dict[str, Any],
        *,
        detector_id: int,
        frame_index: int,
        timestamp_ms: int,
    ) -> None:
        raw_bbox = self._bbox(obj)
        if not raw_bbox:
            return

        if state.bbox:
            predicted_bbox = self._predict_bbox(state.bbox, state.velocity)
            smoothed = self._smooth_bbox(predicted_bbox, raw_bbox)
            state.velocity = [smoothed[i] - state.bbox[i] for i in range(4)]
            state.bbox = smoothed
        else:
            state.bbox = raw_bbox
            state.velocity = [0.0, 0.0, 0.0, 0.0]

        state.detector_ids.add(detector_id)
        state.raw_track_id = detector_id
        state.cls = int(obj.get("cls", 0))
        state.label = str(obj.get("label", "person"))
        state.conf = float(obj.get("conf", 0.0))
        state.hits += 1
        state.age_frames += 1
        state.missed_frames = 0
        state.last_seen_frame = frame_index
        state.last_seen_ms = timestamp_ms
        state.last_update_ms = timestamp_ms
        state.measurement_source = str(obj.get("measurement_source", "full_body"))
        state.last_track_state = "matched"

    def _predict_missing_state(
        self,
        state: TrackState,
        frame_index: int,
        timestamp_ms: int,
    ) -> None:
        state.age_frames += 1
        state.missed_frames += 1
        if state.bbox:
            state.bbox = self._predict_bbox(state.bbox, state.velocity)
        state.conf *= self.config.predicted_conf_decay
        state.last_update_ms = timestamp_ms
        state.last_track_state = "predicted"

    def _state_to_output(self, state: TrackState) -> dict[str, Any] | None:
        if state.hits < self.config.min_hits:
            return None
        if not state.bbox:
            return None

        is_predicted = state.last_track_state == "predicted"
        if is_predicted and not self.config.publish_predicted:
            return None
        if is_predicted and state.conf < self.config.min_predicted_conf:
            return None

        return {
            "id": state.canonical_id,
            "raw_track_id": state.raw_track_id,
            "bbox": [float(v) for v in state.bbox],
            "cls": state.cls,
            "label": state.label,
            "conf": float(max(0.0, min(1.0, state.conf))),
            "track_state": state.last_track_state,
            "measurement_source": state.measurement_source
            if not is_predicted
            else "kalman",
            "age_frames": state.age_frames,
            "missed_frames": state.missed_frames,
            "last_seen_frame": state.last_seen_frame,
            "is_predicted": is_predicted,
            "detector_ids": sorted(state.detector_ids),
        }

    def _match_lost_track(self, obj: dict[str, Any]) -> int | None:
        bbox = self._bbox(obj)
        if not bbox:
            return None

        best_id: int | None = None
        best_score = -1.0
        for canonical_id, state in self._tracks.items():
            if state.missed_frames <= 0 or not state.bbox:
                continue
            if int(obj.get("cls", 0)) != state.cls:
                continue

            iou = self._iou(bbox, state.bbox)
            distance = self._center_distance(bbox, state.bbox)
            distance_score = max(
                0.0,
                1.0 - distance / max(1.0, self.config.reid_center_distance_px),
            )
            score = max(iou, distance_score)
            if (
                iou >= self.config.reid_iou_threshold
                or distance <= self.config.reid_center_distance_px
            ) and score > best_score:
                best_score = score
                best_id = canonical_id

        return best_id

    def _is_dead(
        self,
        state: TrackState,
        frame_index: int,
        timestamp_ms: int,
    ) -> bool:
        if state.missed_frames <= 0:
            return False
        frame_expired = state.missed_frames > self.config.lost_ttl_frames
        time_expired = timestamp_ms - state.last_seen_ms > self.config.lost_ttl_ms
        return frame_expired or time_expired or state.conf < self.config.min_predicted_conf

    def _remove_track(self, canonical_id: int) -> None:
        state = self._tracks.pop(canonical_id, None)
        if state is None:
            return
        for detector_id in state.detector_ids:
            self._detector_to_canonical.pop(detector_id, None)

    def _as_matched_detection(
        self,
        obj: dict[str, Any],
        frame_index: int,
    ) -> dict[str, Any]:
        result = dict(obj)
        result.setdefault("raw_track_id", result.get("id"))
        result.setdefault("track_state", "matched")
        result.setdefault("measurement_source", "full_body")
        result.setdefault("missed_frames", 0)
        result.setdefault("age_frames", 1)
        result.setdefault("last_seen_frame", frame_index)
        result.setdefault("is_predicted", False)
        return result

    def _smooth_bbox(self, predicted: BBox, measured: BBox) -> BBox:
        alpha = max(0.0, min(1.0, self.config.smooth_alpha))
        return [alpha * measured[i] + (1.0 - alpha) * predicted[i] for i in range(4)]

    @staticmethod
    def _detector_id(obj: dict[str, Any]) -> int | None:
        raw_id = obj.get("id")
        try:
            detector_id = int(raw_id)
        except (TypeError, ValueError):
            return None
        return detector_id if detector_id >= 0 else None

    @staticmethod
    def _bbox(obj: dict[str, Any]) -> BBox:
        raw = obj.get("bbox")
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            return []
        try:
            x1, y1, x2, y2 = [float(v) for v in raw]
        except (TypeError, ValueError):
            return []
        if x2 <= x1 or y2 <= y1:
            return []
        return [x1, y1, x2, y2]

    @staticmethod
    def _predict_bbox(bbox: BBox, velocity: BBox) -> BBox:
        return [bbox[i] + velocity[i] for i in range(4)]

    @staticmethod
    def _iou(a: BBox, b: BBox) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        iw = max(0.0, ix2 - ix1)
        ih = max(0.0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _center_distance(a: BBox, b: BBox) -> float:
        acx = (a[0] + a[2]) / 2.0
        acy = (a[1] + a[3]) / 2.0
        bcx = (b[0] + b[2]) / 2.0
        bcy = (b[1] + b[3]) / 2.0
        return ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5
