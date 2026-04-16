from .deepsort_tracker import DeepSORTTracker
from .yolo_tracker_botsort import YoloBoTSORTTracker
from .yolo_tracker_bytetrack import YoloByteTracker


def create_tracker(tracker_name: str, model_name: str, **kwargs):
    tracker = tracker_name.lower().strip()
    conf_thres = float(kwargs.get("conf_thres", 0.25))

    if tracker == "botsort":
        return YoloBoTSORTTracker(model_name, conf_thres=conf_thres)
    if tracker == "bytetrack":
        return YoloByteTracker(model_name, conf_thres=conf_thres)
    if tracker == "deepsort":
        return DeepSORTTracker(model_name, conf_thres=conf_thres)

    raise ValueError(f"Unknown tracker: {tracker_name}. Supported: botsort | bytetrack | deepsort")
