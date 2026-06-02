"""Retail polygon zone and line-crossing runtime helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from features.detections import bottom_center

logger = logging.getLogger(__name__)

try:
    import supervision as sv
except Exception:  # pragma: no cover
    sv = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ZoneSpec:
    zone_id: str
    zone_name: str
    zone_type: str
    polygon_norm: list[list[float]]
    priority: int = 0


@dataclass(frozen=True)
class LineSpec:
    line_id: str
    line_name: str
    line_type: str
    start_norm: list[float]
    end_norm: list[float]
    direction_in: str = "negative_to_positive"


class RetailZoneRuntime:
    def __init__(self, *, version: str, zones: list[ZoneSpec], lines: list[LineSpec]) -> None:
        self.version = version
        self.zones = zones
        self.lines = lines
        self._previous_line_state: dict[tuple[str, str], tuple[int, tuple[float, float]]] = {}
        self._polygon_zone_cache: dict[tuple[str, int, int], Any] = {}

    @classmethod
    def from_config_path(cls, path: str | None, store_id: str, camera_id: str) -> "RetailZoneRuntime":
        if not path:
            return cls(version="none", zones=[], lines=[])
        config_path = Path(path)
        if not config_path.exists():
            logger.warning("Zone config not found: %s", config_path)
            return cls(version="missing", zones=[], lines=[])

        payload = yaml.safe_load(config_path.read_text()) or {}
        version = str(payload.get("version", "unknown"))
        camera_cfg = (
            payload.get("stores", {})
            .get(store_id, {})
            .get("cameras", {})
            .get(camera_id, {})
        )
        zones = [
            ZoneSpec(
                zone_id=str(item["zone_id"]),
                zone_name=str(item.get("zone_name", item["zone_id"])),
                zone_type=str(item.get("zone_type", "dwell")),
                polygon_norm=[[float(x), float(y)] for x, y in item.get("polygon_norm", [])],
                priority=int(item.get("priority", 0)),
            )
            for item in camera_cfg.get("zones", [])
            if item.get("zone_id") and item.get("polygon_norm")
        ]
        lines = [
            LineSpec(
                line_id=str(item["line_id"]),
                line_name=str(item.get("line_name", item["line_id"])),
                line_type=str(item.get("line_type", "crossing")),
                start_norm=[float(v) for v in item.get("start_norm", [0, 0])],
                end_norm=[float(v) for v in item.get("end_norm", [1, 1])],
                direction_in=str(item.get("direction_in", "negative_to_positive")),
            )
            for item in camera_cfg.get("lines", [])
            if item.get("line_id")
        ]
        logger.info("Loaded zone config %s: zones=%d lines=%d", version, len(zones), len(lines))
        return cls(version=version, zones=zones, lines=lines)

    def assign(self, tracks: list[dict[str, Any]], width: int, height: int) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
        assignments: list[list[dict[str, Any]]] = [[] for _ in tracks]
        zone_counts: list[dict[str, Any]] = []
        if not self.zones or not tracks:
            return assignments, zone_counts

        for spec in sorted(self.zones, key=lambda item: item.priority, reverse=True):
            mask = self._trigger_zone(spec, tracks, width, height)
            track_ids: list[int] = []
            global_track_ids: list[str] = []
            for idx, inside in enumerate(mask):
                if not inside:
                    continue
                zone_record = {
                    "zone_id": spec.zone_id,
                    "zone_name": spec.zone_name,
                    "zone_type": spec.zone_type,
                    "is_primary": False,
                }
                assignments[idx].append(zone_record)
                raw_track_id = tracks[idx].get("id")
                if isinstance(raw_track_id, int):
                    track_ids.append(raw_track_id)
                global_id = tracks[idx].get("global_track_id")
                if global_id:
                    global_track_ids.append(str(global_id))

            zone_counts.append(
                {
                    "zone_id": spec.zone_id,
                    "zone_type": spec.zone_type,
                    "count": int(sum(bool(v) for v in mask)),
                    "track_ids": track_ids,
                    "global_track_ids": global_track_ids,
                }
            )

        for zones in assignments:
            if zones:
                zones[0]["is_primary"] = True
        return assignments, zone_counts

    def trigger_lines(self, tracks: list[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
        crossings: list[dict[str, Any]] = []
        if not self.lines or not tracks:
            return crossings

        for spec in self.lines:
            start = _norm_point(spec.start_norm, width, height)
            end = _norm_point(spec.end_norm, width, height)
            for track in tracks:
                global_id = str(track.get("global_track_id") or track.get("id") or "")
                if not global_id:
                    continue
                point = bottom_center(track)
                side = _line_side(start, end, point)
                side_sign = 1 if side >= 0 else -1
                key = (spec.line_id, global_id)
                previous = self._previous_line_state.get(key)
                self._previous_line_state[key] = (side_sign, point)
                if previous is None or previous[0] == side_sign:
                    continue
                direction = _crossing_direction(spec.direction_in, previous[1], point, previous[0], side_sign)
                crossings.append(
                    {
                        "line_id": spec.line_id,
                        "line_type": spec.line_type,
                        "direction": direction,
                        "track_id": track.get("id"),
                        "raw_track_id": track.get("raw_track_id"),
                        "global_track_id": track.get("global_track_id"),
                    }
                )
        return crossings

    def draw_overlays(self, frame: np.ndarray, width: int, height: int, zone_counts: list[dict[str, Any]]) -> np.ndarray:
        count_by_zone = {item.get("zone_id"): item.get("count", 0) for item in zone_counts}
        for spec in self.zones:
            polygon = _polygon_px(spec.polygon_norm, width, height)
            if len(polygon) < 3:
                continue
            cv2.polylines(frame, [polygon], isClosed=True, color=(41, 171, 226), thickness=2)
            label_point = tuple(polygon[0].astype(int).tolist())
            label = f"{spec.zone_id}: {count_by_zone.get(spec.zone_id, 0)}"
            cv2.putText(frame, label, label_point, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (41, 171, 226), 1)

        for spec in self.lines:
            start = tuple(map(int, _norm_point(spec.start_norm, width, height)))
            end = tuple(map(int, _norm_point(spec.end_norm, width, height)))
            cv2.line(frame, start, end, (0, 220, 120), 2)
            cv2.putText(frame, spec.line_id, start, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 120), 1)
        return frame

    def _trigger_zone(self, spec: ZoneSpec, tracks: list[dict[str, Any]], width: int, height: int) -> list[bool]:
        if sv is not None:
            detections = _tracks_to_sv_detections(tracks)
            if detections is not None:
                zone = self._polygon_zone(spec, width, height)
                if zone is not None:
                    try:
                        return [bool(v) for v in zone.trigger(detections)]
                    except Exception:
                        logger.debug("Supervision PolygonZone trigger failed; using manual fallback", exc_info=True)
        polygon = _polygon_px(spec.polygon_norm, width, height)
        return [_point_in_polygon(bottom_center(track), polygon) for track in tracks]

    def _polygon_zone(self, spec: ZoneSpec, width: int, height: int):
        key = (spec.zone_id, width, height)
        if key in self._polygon_zone_cache:
            return self._polygon_zone_cache[key]
        if sv is None:
            return None
        polygon = _polygon_px(spec.polygon_norm, width, height)
        try:
            zone = sv.PolygonZone(
                polygon=polygon,
                triggering_anchors=(sv.Position.BOTTOM_CENTER,),
            )
        except TypeError:
            zone = sv.PolygonZone(polygon=polygon)
        self._polygon_zone_cache[key] = zone
        return zone


def _tracks_to_sv_detections(tracks: list[dict[str, Any]]):
    if sv is None or not tracks:
        return None
    try:
        xyxy = np.asarray([track["bbox"] for track in tracks], dtype=float)
        confidence = np.asarray([float(track.get("conf", 0.0)) for track in tracks], dtype=float)
        class_id = np.asarray([int(track.get("cls", 0)) for track in tracks], dtype=int)
        tracker_id = np.asarray([int(track.get("id", -1)) for track in tracks], dtype=int)
        return sv.Detections(
            xyxy=xyxy,
            confidence=confidence,
            class_id=class_id,
            tracker_id=tracker_id,
        )
    except Exception:
        return None


def _polygon_px(points: list[list[float]], width: int, height: int) -> np.ndarray:
    return np.asarray([[int(x * width), int(y * height)] for x, y in points], dtype=np.int32)


def _norm_point(point: list[float], width: int, height: int) -> tuple[float, float]:
    return (float(point[0]) * width, float(point[1]) * height)


def _point_in_polygon(point: tuple[float, float], polygon: np.ndarray) -> bool:
    if len(polygon) < 3:
        return False
    return cv2.pointPolygonTest(polygon, point, False) >= 0


def _line_side(start: tuple[float, float], end: tuple[float, float], point: tuple[float, float]) -> float:
    return (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (point[0] - start[0])


def _crossing_direction(
    direction_in: str,
    previous_point: tuple[float, float],
    current_point: tuple[float, float],
    previous_side: int,
    current_side: int,
) -> str:
    if direction_in == "left_to_right":
        return "in" if current_point[0] >= previous_point[0] else "out"
    if direction_in == "right_to_left":
        return "in" if current_point[0] <= previous_point[0] else "out"
    if direction_in == "top_to_bottom":
        return "in" if current_point[1] >= previous_point[1] else "out"
    if direction_in == "bottom_to_top":
        return "in" if current_point[1] <= previous_point[1] else "out"
    return "in" if previous_side < current_side else "out"
