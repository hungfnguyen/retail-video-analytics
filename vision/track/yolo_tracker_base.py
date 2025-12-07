# track/yolo_tracker_base.py
from pathlib import Path
from typing import Dict, Iterator, List, Any
import os
from ultralytics import YOLO
from utils.path_utils import resolve_model_path, resolve_tracker_config

class YoloTrackerBase:
    """
    Base tracker dùng Ultralytics .track()
    Các lớp con chỉ cần truyền tên yaml ('botsort.yaml' hoặc 'bytetrack.yaml')
    """
    def __init__(self, model_name: str, tracker_yaml: str):
        model_path = resolve_model_path(model_name)
        print(f"[Tracker] Loading model: {model_path}")
        self.model = YOLO(model_path)
        self.tracker_yaml = resolve_tracker_config(tracker_yaml)
        
        # Auto-detect device (GPU if available, else CPU)
        # Override: Force GPU với environment variable FORCE_GPU=1
        force_gpu = os.getenv("FORCE_GPU", "0") == "1"
        try:
            import torch
            if force_gpu:
                self.device = 0
                print(f"[Tracker] Device: GPU (cuda:0) - FORCED via FORCE_GPU=1")
            else:
                self.device = 0 if torch.cuda.is_available() else 'cpu'
                device_name = f"GPU (cuda:{self.device})" if self.device == 0 else "CPU"
                print(f"[Tracker] Device: {device_name}")
        except ImportError:
            self.device = 'cpu'
            print(f"[Tracker] Device: CPU (torch not available)")
        
        print(f"[Tracker] Tracker config: {self.tracker_yaml}")
        print("-" * 60)

    def track(self, source: str, show=False, save=False, classes=None) -> Iterator[Dict[str, Any]]:
        """
        Track objects trong video/stream.
        
        Args:
            source: đường dẫn video hoặc stream URL
            show: hiển thị kết quả realtime
            save: lưu kết quả
            classes: list các class ID cần track (vd: [0] cho person, [0,2,5] cho nhiều class)
                    None = track tất cả
        """
        # Cho phép chỉnh ngưỡng detect qua ENV để debug occlusion nhanh
        track_conf = float(os.getenv("YOLO_TRACK_CONF", "0.20"))
        results_gen = self.model.track(
            source=source,
            show=show,
            save=save,
            tracker=self.tracker_yaml,
            classes=classes,  # filter class
            conf=track_conf,
            device=self.device,  # Auto-detected: GPU if available, else CPU
            stream=True,
            verbose=False
        )
        for i, r in enumerate(results_gen):
            yield {
                "frame_index": i,
                "type": "track",
                "frame": r.orig_img,  # thêm frame gốc
                "objects": self._extract_objects(r)
            }

    def _extract_objects(self, r) -> List[Dict[str, Any]]:
        objs = []
        if getattr(r, "boxes", None) is None or getattr(r.boxes, "xyxy", None) is None:
            return objs

        xyxy = r.boxes.xyxy.cpu().numpy()
        conf = r.boxes.conf.cpu().numpy() if getattr(r.boxes, "conf", None) is not None else []
        cls_ = r.boxes.cls.cpu().numpy().astype(int) if getattr(r.boxes, "cls", None) is not None else []
        ids  = r.boxes.id.cpu().numpy().astype(int) if getattr(r.boxes, "id", None) is not None else [-1] * len(xyxy)

        for j, box in enumerate(xyxy):
            x1, y1, x2, y2 = map(float, box)
            cls_id = int(cls_[j]) if j < len(cls_) else -1
            objs.append({
                "id": int(ids[j]) if j < len(ids) else -1,
                "bbox": [x1, y1, x2, y2],
                "cls": cls_id,
                "label": r.names[cls_id] if cls_id >= 0 else "unknown",  # thêm tên class
                "conf": float(conf[j]) if j < len(conf) else 0.0,
            })
        return objs
