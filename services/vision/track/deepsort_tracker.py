# services/vision/track/deepsort_tracker.py

import os
from typing import Any, Dict, Iterator, List

from deep_sort_realtime.deepsort_tracker import DeepSort

from detect.yolo_detector import YoloDetector
from ingest.CVSource import ingest_video


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value != "" else default


class DeepSORTTracker:
    """
    DeepSORT tracker using deep-sort-realtime + YOLO detector.

    This differs from BoTSORT/ByteTrack because it does not use Ultralytics `.track()`.
    """

    def __init__(self, model_name: str, conf_thres: float = 0.25):
        print("[DeepSORT] Initializing DeepSORT tracker")

        max_age = int(float(_get_env("DS_MAX_AGE", "90")))
        n_init = int(float(_get_env("DS_N_INIT", "3")))
        max_iou_distance = float(_get_env("DS_MAX_IOU_DISTANCE", "0.7"))
        embedder = _get_env("DEEPSORT_EMBEDDER", "mobilenet")  # mobilenet | torchreid
        embedder_gpu = _get_env("DEEPSORT_EMBEDDER_GPU", "1") in {"1", "true", "True"}
        det_conf = float(_get_env("DS_DET_CONF", str(conf_thres)))

        self.nms_iou = float(_get_env("DS_NMS_IOU", "0.6"))
        self.smooth_alpha = float(_get_env("DS_SMOOTH_ALPHA", "0.6"))
        self.smooth_min_iou = float(_get_env("DS_SMOOTH_MIN_IOU", "0.10"))
        self._prev_boxes: Dict[int, List[float]] = {}

        print(f"[DeepSORT] Model={model_name}, YOLO conf={det_conf}")

        self.detector = YoloDetector(model_name=model_name, conf_thres=det_conf)

        try:
            self.tracker = DeepSort(
                max_age=max_age,
                n_init=n_init,
                max_iou_distance=max_iou_distance,
                embedder=embedder,
                embedder_gpu=embedder_gpu,
            )
        except Exception as e:
            if embedder == "torchreid":
                print(f"[DeepSORT] Embedder 'torchreid' failed ({e}); falling back to 'mobilenet'")
                self.tracker = DeepSort(
                    max_age=max_age,
                    n_init=n_init,
                    max_iou_distance=max_iou_distance,
                    embedder="mobilenet",
                    embedder_gpu=embedder_gpu,
                )
            else:
                raise

        print("[DeepSORT] Tracker initialized")
        print("-" * 60)

    def track(self, source: str, show: bool = False, classes: List[int] = None) -> Iterator[Dict[str, Any]]:
        if show:
            raise ValueError("DeepSORTTracker.track(show=True) is not supported. Use a Visualizer outside.")

        for idx, item in enumerate(ingest_video(source, realtime=False), start=0):
            frame = item["frame"]

            detections = self.detector.predict(frame, class_filter=classes)
            detections = self._suppress_overlaps(detections)

            det_info_map: Dict[int, Dict[str, Any]] = {}
            deepsort_detections = []
            for i, det in enumerate(detections):
                x1, y1, x2, y2 = det["bbox"]
                w = x2 - x1
                h = y2 - y1
                det_info_map[i] = {"cls": det["cls"], "label": det["label"], "conf": det["conf"]}
                deepsort_detections.append(([x1, y1, w, h], det["conf"], str(i)))

            tracks = self.tracker.update_tracks(deepsort_detections, frame=frame)

            objects = []
            height, width = frame.shape[:2]
            for track in tracks:
                if not track.is_confirmed():
                    continue

                track_id = int(track.track_id)
                x1, y1, x2, y2 = track.to_ltrb()

                x1, y1, x2, y2 = self._smooth_and_clip_bbox(track_id, [x1, y1, x2, y2], frame_h=height, frame_w=width)

                det_class_str = track.det_class if hasattr(track, "det_class") else "0"
                try:
                    det_idx = int(det_class_str)
                except ValueError:
                    det_idx = 0

                det_info = det_info_map.get(det_idx, {})
                objects.append(
                    {
                        "id": track_id,
                        "bbox": [float(x1), float(y1), float(x2), float(y2)],
                        "cls": int(det_info.get("cls", 0)),
                        "label": str(det_info.get("label", "person")),
                        "conf": float(det_info.get("conf", 0.0)),
                    }
                )

            yield {"frame_index": idx, "type": "track", "frame": frame, "objects": objects}

    def _suppress_overlaps(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not detections:
            return detections

        dets = sorted(detections, key=lambda d: d.get("conf", 0.0), reverse=True)
        kept: List[Dict[str, Any]] = []

        for d in dets:
            x1, y1, x2, y2 = d["bbox"]
            area1 = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            should_keep = True

            for k in kept:
                if d.get("cls") != k.get("cls"):
                    continue
                kx1, ky1, kx2, ky2 = k["bbox"]

                xx1 = max(x1, kx1)
                yy1 = max(y1, ky1)
                xx2 = min(x2, kx2)
                yy2 = min(y2, ky2)

                w = max(0.0, xx2 - xx1)
                h = max(0.0, yy2 - yy1)
                inter = w * h
                if inter <= 0:
                    continue

                area2 = max(0.0, kx2 - kx1) * max(0.0, ky2 - ky1)
                union = area1 + area2 - inter
                iou = inter / union if union > 0 else 0.0

                if iou >= self.nms_iou:
                    should_keep = False
                    break

            if should_keep:
                kept.append(d)

        return kept

    def _smooth_and_clip_bbox(self, track_id: int, bbox: List[float], frame_h: int, frame_w: int) -> List[float]:
        x1, y1, x2, y2 = bbox

        x1 = max(0.0, min(float(frame_w - 1), float(x1)))
        y1 = max(0.0, min(float(frame_h - 1), float(y1)))
        x2 = max(x1 + 1.0, min(float(frame_w), float(x2)))
        y2 = max(y1 + 1.0, min(float(frame_h), float(y2)))
        curr = [x1, y1, x2, y2]

        prev = self._prev_boxes.get(track_id)
        if prev:
            iou = self._bbox_iou(curr, prev)
            if iou >= self.smooth_min_iou:
                alpha = self.smooth_alpha
                curr = [alpha * curr[i] + (1 - alpha) * prev[i] for i in range(4)]

        self._prev_boxes[track_id] = curr
        return curr

    @staticmethod
    def _bbox_iou(a: List[float], b: List[float]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b

        xx1 = max(ax1, bx1)
        yy1 = max(ay1, by1)
        xx2 = min(ax2, bx2)
        yy2 = min(ay2, by2)

        w = max(0.0, xx2 - xx1)
        h = max(0.0, yy2 - yy1)
        inter = w * h
        if inter <= 0:
            return 0.0

        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0
