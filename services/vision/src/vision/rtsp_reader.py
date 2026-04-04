"""Background thread RTSP reader with frame dropping and auto-reconnect.

Design:
- One RTSPReader instance per camera, running in its CameraWorker subprocess.
- A background daemon thread calls cv2.VideoCapture.read() continuously.
- Frames are placed into a Queue(maxsize=2); when the queue is full the oldest
  frame is discarded so the consumer always receives the latest frame.
- On read failure the thread closes the capture and reconnects using
  exponential backoff capped at reconnect_delay_max seconds.
"""

import logging
import time
from dataclasses import dataclass, field
from queue import Empty, Full, Queue
from threading import Event, Thread

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RTSPConfig:
    """Configuration for one RTSP stream."""

    url: str
    queue_size: int = 2
    reconnect_delay_initial: float = 1.0   # seconds
    reconnect_delay_max: float = 30.0      # seconds (exponential backoff cap)
    open_timeout_ms: int = 5000            # cv2.CAP_PROP_OPEN_TIMEOUT_MSEC


class RTSPReader:
    """Thread-based RTSP reader with frame dropping and auto-reconnect.

    Usage::

        reader = RTSPReader(camera_id="cam_01", config=RTSPConfig(url="rtsp://..."))
        reader.start()

        while True:
            ok, frame = reader.get_frame()
            if ok:
                process(frame)

        reader.stop()
    """

    def __init__(self, camera_id: str, config: RTSPConfig) -> None:
        self.camera_id = camera_id
        self.config = config

        # Frame queue: maxsize=2 ensures consumer always gets fresh frames.
        # When full, _reader_loop drops the oldest entry before enqueuing.
        self._queue: Queue[np.ndarray] = Queue(maxsize=config.queue_size)

        self._stop_event = Event()
        self._thread: Thread | None = None
        self._cap: cv2.VideoCapture | None = None

    # ── Public API ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background reader thread."""
        # TODO: create daemon thread targeting _reader_loop, then thread.start()
        raise NotImplementedError

    def stop(self) -> None:
        """Signal the reader thread to stop and release the capture device."""
        # TODO: set _stop_event, join thread with timeout, release _cap
        raise NotImplementedError

    def get_frame(self) -> tuple[bool, np.ndarray | None]:
        """Non-blocking fetch of the latest available frame.

        Returns:
            (True, frame)  when a frame is available.
            (False, None)  when the queue is empty (no new frame yet).
        """
        # TODO: queue.get_nowait(), handle Empty exception
        raise NotImplementedError

    def is_alive(self) -> bool:
        """Return True if the reader thread is running."""
        # TODO: return self._thread is not None and self._thread.is_alive()
        raise NotImplementedError

    # ── Private ─────────────────────────────────────────────────────────────

    def _connect(self) -> bool:
        """Open the RTSP stream.

        Steps:
        1. Release existing capture if any.
        2. cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        3. Set CAP_PROP_BUFFERSIZE = 1 to minimise OS-level buffering.
        4. Set CAP_PROP_OPEN_TIMEOUT_MSEC to avoid indefinite hang.
        5. Return cap.isOpened().
        """
        # TODO: implement connection with timeout and buffer size settings
        raise NotImplementedError

    def _reader_loop(self) -> None:
        """Main loop executed on the background thread.

        Algorithm:
        1. Call _connect(). If it fails, wait reconnect_delay_initial and retry.
        2. Loop: cap.read() → on success enqueue frame (drop oldest if full).
        3. On read failure (ret=False or exception):
           a. Close capture.
           b. Wait delay = min(delay * 2, reconnect_delay_max) seconds.
           c. Go to step 1.
        4. Exit when _stop_event is set.
        """
        # TODO: implement main loop with exponential backoff reconnect
        raise NotImplementedError
