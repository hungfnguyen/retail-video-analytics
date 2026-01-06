from .yolo_tracker_base import YoloTrackerBase


class YoloByteTracker(YoloTrackerBase):
    def __init__(self, model_name: str, conf_thres: float = 0.25):
        super().__init__(model_name, "bytetrack.yaml", track_conf=conf_thres)
