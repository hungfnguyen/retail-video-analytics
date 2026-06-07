from __future__ import annotations

import logging
import queue
import signal
import time
from dataclasses import dataclass
from multiprocessing import Queue
from typing import Any

import numpy as np

from detect.supervision_yolo_detector import SupervisionYoloDetector

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SharedInferenceHandles:
    request_queue: Queue
    response_queues: dict[str, Queue]


class SharedInferenceClient:
    """Camera-worker client for the single shared YOLO inference process."""

    detector_type = "shared_ultralytics_yolo"

    def __init__(
        self,
        *,
        camera_id: str,
        request_queue: Queue,
        response_queue: Queue,
        timeout_sec: float = 30.0,
    ) -> None:
        self.camera_id = camera_id
        self.request_queue = request_queue
        self.response_queue = response_queue
        self.timeout_sec = float(timeout_sec)
        self.names: dict[int, str] = {}
        self._sequence = 0

    def predict(self, frame: np.ndarray):
        request_id = f"{self.camera_id}:{self._sequence}"
        self._sequence += 1
        self._drain_stale_responses()

        self.request_queue.put(
            {
                "type": "predict",
                "camera_id": self.camera_id,
                "request_id": request_id,
                "frame": frame,
                "sent_monotonic": time.perf_counter(),
            },
            timeout=self.timeout_sec,
        )

        deadline = time.perf_counter() + self.timeout_sec
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TimeoutError(
                    f"Shared inference timed out for camera={self.camera_id}"
                )

            response = self.response_queue.get(timeout=remaining)
            if response.get("request_id") != request_id:
                continue
            if response.get("error"):
                raise RuntimeError(response["error"])

            self.names = response.get("names", self.names) or self.names
            return response["detections"]

    def _drain_stale_responses(self) -> None:
        while True:
            try:
                self.response_queue.get_nowait()
            except queue.Empty:
                return


def run_shared_yolo_inference(
    global_cfg: dict[str, Any],
    request_queue: Queue,
    response_queues: dict[str, Queue],
) -> None:
    """Run a single YOLO model process and serve all camera workers."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [shared-inference] %(levelname)s %(message)s",
    )
    running = True

    def _shutdown(signum, frame):
        nonlocal running
        logger.info("Received signal %s, shutting down shared inference...", signum)
        running = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    class_filter = global_cfg.get("class_filter", [0])
    logger.info(
        "Loading shared YOLO detector: model=%s conf=%.2f imgsz=%s",
        global_cfg["model_name"],
        float(global_cfg.get("conf_thres", 0.15)),
        global_cfg.get("detector_imgsz", 1280),
    )
    detector = SupervisionYoloDetector(
        global_cfg["model_name"],
        conf_thres=float(global_cfg.get("conf_thres", 0.15)),
        class_filter=class_filter,
        iou=float(global_cfg.get("detector_iou", 0.70)),
        imgsz=global_cfg.get("detector_imgsz", 1280),
        half=bool(global_cfg.get("detector_half", True)),
    )
    logger.info("Shared YOLO detector ready")

    while running:
        try:
            request = request_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        if request.get("type") == "stop":
            break

        camera_id = request.get("camera_id")
        response_queue = response_queues.get(camera_id)
        if response_queue is None:
            logger.warning("Dropping inference response for unknown camera=%s", camera_id)
            continue

        response: dict[str, Any] = {
            "request_id": request.get("request_id"),
            "camera_id": camera_id,
            "names": detector.names,
            "detector_type": detector.detector_type,
        }
        try:
            response["detections"] = detector.predict(request["frame"])
            response["error"] = None
        except Exception as exc:
            logger.exception("Shared inference failed for camera=%s", camera_id)
            response["error"] = str(exc)

        _put_latest_response(response_queue, response)

    logger.info("Shared inference stopped")


def _put_latest_response(response_queue: Queue, response: dict[str, Any]) -> None:
    while True:
        try:
            response_queue.put_nowait(response)
            return
        except queue.Full:
            try:
                response_queue.get_nowait()
            except queue.Empty:
                continue

