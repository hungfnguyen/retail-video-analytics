import os
from typing import Any, Dict, Iterator, List

from ultralytics import YOLO

from utils.path_utils import resolve_model_path, resolve_tracker_config


class YoloTrackerBase:
    """
    Base tracker using Ultralytics `.track()`.

    Subclasses only need to pass the tracker YAML name ('botsort.yaml' or 'bytetrack.yaml').
    """

    def __init__(self, model_name: str, tracker_yaml: str, track_conf: float = 0.20):
        model_path = resolve_model_path(model_name)
        print(f"[Tracker] Loading model: {model_path}")

        self.model = YOLO(model_path)
        self.tracker_yaml = resolve_tracker_config(tracker_yaml)
        self.track_conf = float(os.getenv("YOLO_TRACK_CONF", str(track_conf)))

        force_gpu = os.getenv("FORCE_GPU", "0") == "1"
        try:
            import torch

            if force_gpu:
                if not torch.cuda.is_available():
                    raise RuntimeError(
                        "FORCE_GPU=1 but CUDA is not available. Run Vision with the project .venv "
                        "or install a CUDA-enabled PyTorch build."
                    )
                self.device = 0
                print("[Tracker] Device: GPU (cuda:0) - forced via FORCE_GPU=1")
            else:
                self.device = 0 if torch.cuda.is_available() else "cpu"
                device_name = "GPU (cuda:0)" if self.device == 0 else "CPU"
                print(f"[Tracker] Device: {device_name}")
        except ImportError:
            self.device = "cpu"
            print("[Tracker] Device: CPU (torch not available)")

        print(f"[Tracker] Tracker config: {self.tracker_yaml}")
        print("-" * 60)

    def track(self, source: str, show: bool = False, save: bool = False, classes=None) -> Iterator[Dict[str, Any]]:
        """
        Track objects in a video/stream.

        Args:
            source: video path or stream URL
            show: display realtime results
            save: save output
            classes: list of class IDs to track (e.g., [0] for person). Use None for all classes.
        """
        results_gen = self.model.track(
            source=source,
            show=show,
            save=save,
            tracker=self.tracker_yaml,
            classes=classes,
            conf=self.track_conf,
            device=self.device,
            stream=True,
            verbose=False,
        )
        for i, r in enumerate(results_gen):
            yield {"frame_index": i, "type": "track", "frame": r.orig_img, "objects": self._extract_objects(r)}

    def _extract_objects(self, r) -> List[Dict[str, Any]]:
        objs: List[Dict[str, Any]] = []
        if getattr(r, "boxes", None) is None or getattr(r.boxes, "xyxy", None) is None:
            return objs

        xyxy = r.boxes.xyxy.cpu().numpy()
        conf = r.boxes.conf.cpu().numpy() if getattr(r.boxes, "conf", None) is not None else []
        cls_ = r.boxes.cls.cpu().numpy().astype(int) if getattr(r.boxes, "cls", None) is not None else []
        ids = r.boxes.id.cpu().numpy().astype(int) if getattr(r.boxes, "id", None) is not None else [-1] * len(xyxy)

        for j, box in enumerate(xyxy):
            x1, y1, x2, y2 = map(float, box)
            cls_id = int(cls_[j]) if j < len(cls_) else -1
            objs.append(
                {
                    "id": int(ids[j]) if j < len(ids) else -1,
                    "bbox": [x1, y1, x2, y2],
                    "cls": cls_id,
                    "label": r.names[cls_id] if cls_id >= 0 else "unknown",
                    "conf": float(conf[j]) if j < len(conf) else 0.0,
                }
            )
        return objs
