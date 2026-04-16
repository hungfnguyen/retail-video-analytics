# vision/detect/yolo_detector.py

from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

from utils.path_utils import resolve_model_path


class YoloDetector:
    """
    YOLO11 (Ultralytics) detector wrapper.

    - Automatically selects GPU if available, otherwise CPU.
    - Runs inference on a single frame (numpy BGR image).
    - Returns a list of dicts: [{bbox, conf, cls, label}, ...]
    """

    def __init__(self, model_name: str = "yolo11s.pt", conf_thres: float = 0.2):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_path = resolve_model_path(model_name)

        print(f"[YOLO] Loading model on device: {self.device}")
        print(f"[YOLO] Model path: {self.model_path}")

        self.model = YOLO(self.model_path)
        self.model.to(self.device)
        self.conf_thres = conf_thres
        self.names = self.model.names

    def predict(self, frame: np.ndarray, class_filter=None):
        # Ultralytics expects RGB input.
        results = self.model.predict(
            source=frame[..., ::-1],
            verbose=False,
            conf=self.conf_thres,
            device=self.device,
        )

        detections = []
        if not results:
            return detections

        r = results[0]
        boxes = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        classes = r.boxes.cls.cpu().numpy().astype(int)

        for i in range(len(boxes)):
            cls_id = int(classes[i])
            if class_filter and cls_id not in class_filter:
                continue

            x1, y1, x2, y2 = boxes[i].tolist()
            detections.append(
                {
                    "bbox": [x1, y1, x2, y2],
                    "conf": float(confs[i]),
                    "cls": cls_id,
                    "label": r.names[cls_id],
                }
            )
        return detections
