import cv2
import numpy as np
from typing import Dict, List, Any, Tuple


class Visualizer:
    """Draw bounding boxes and compact live labels onto frames."""

    def __init__(self, font_scale: float = 0.45, thickness: int = 1):
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.font_scale = font_scale
        self.thickness = thickness
        self.bbox_color = (255, 191, 0)
        self.predicted_bbox_color = (0, 191, 255)
        self.text_color = (0, 0, 0)

    def draw_tracks(self, frame: np.ndarray, tracks: List[Dict[str, Any]]) -> np.ndarray:
        for obj in tracks:
            bbox = obj.get("bbox")
            if not bbox:
                continue

            x1, y1, x2, y2 = map(int, bbox)
            track_id = obj.get("id", -1)
            track_state = obj.get("track_state", "matched")
            if track_state == "predicted":
                color = self.predicted_bbox_color
            else:
                color = self.bbox_color

            display_text = self._label_for_track(obj, track_id)
            self._draw_box_and_label(frame, (x1, y1, x2, y2), display_text, color)

        return frame

    def _label_for_track(self, obj: Dict[str, Any], track_id: Any) -> str:
        try:
            safe_track_id = int(track_id)
        except (TypeError, ValueError):
            safe_track_id = -1

        if safe_track_id >= 0:
            label = f"#{safe_track_id:02d}"
        else:
            label = "#--"

        wait_seconds = int(obj.get("queue_wait_seconds", 0) or 0)
        if wait_seconds > 0 and obj.get("primary_zone_type") == "queue":
            label = f"{label} {self._format_duration(wait_seconds)}"

        return label

    @staticmethod
    def _format_duration(total_seconds: int) -> str:
        minutes, seconds = divmod(max(0, total_seconds), 60)
        if minutes > 0:
            return f"{minutes}m{seconds:02d}s"
        return f"{seconds}s"

    def _draw_box_and_label(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        text: str,
        color: Tuple[int, int, int],
    ):
        x1, y1, x2, y2 = bbox

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        (text_w, text_h), baseline = cv2.getTextSize(
            text, self.font, self.font_scale, self.thickness
        )

        cv2.rectangle(
            frame,
            (x1, y1 - text_h - baseline - 5),
            (x1 + text_w, y1),
            color,
            -1,
        )

        cv2.putText(
            frame,
            text,
            (x1, y1 - baseline - 2),
            self.font,
            self.font_scale,
            self.text_color,
            self.thickness,
        )
