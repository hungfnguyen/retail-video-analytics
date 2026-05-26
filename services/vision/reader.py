import queue
import time
import logging
import threading

import cv2

logger = logging.getLogger(__name__)


class VideoFileReader:
    """Đọc video file trong thread riêng, push frame vào queue.Queue.

    - Thread-safe queue.Queue(maxsize)
    - Drop frame cũ nhất khi queue đầy
    - Giả lập FPS thật (realtime mode)
    - Tự động loop về đầu khi hết video
    """

    def __init__(
        self,
        video_path: str,
        fps_target: int = 25,
        queue_size: int = 2,
        realtime: bool = True,
        loop: bool = True,
    ):
        self.video_path = video_path
        self.fps_target = fps_target
        self.realtime = realtime
        self.loop = loop
        self.queue: queue.Queue = queue.Queue(maxsize=queue_size)

        self._thread: threading.Thread | None = None
        self._running = False

        # Metrics
        self.total_read = 0
        self.drop_count = 0

    def start(self) -> None:
        """Bắt đầu reader thread."""
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info("VideoFileReader started: %s (fps=%d)", self.video_path, self.fps_target)

    def stop(self) -> None:
        """Dừng reader thread và đợi join."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        logger.info("VideoFileReader stopped: read=%d drop=%d", self.total_read, self.drop_count)

    def _read_loop(self) -> None:
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            logger.error("Cannot open video: %s", self.video_path)
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or self.fps_target
        t0 = time.perf_counter()
        seq = 0

        while self._running:
            ret, frame = cap.read()
            if not ret:
                if self.loop:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    seq = 0
                    t0 = time.perf_counter()
                    continue
                else:
                    break

            # Giả lập FPS
            if self.realtime:
                due = t0 + seq / fps
                now = time.perf_counter()
                if due > now:
                    time.sleep(due - now)

            # Drop frame cũ nhất nếu queue đầy
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                    self.drop_count += 1
                except queue.Empty:
                    pass

            self.queue.put(frame)
            self.total_read += 1
            seq += 1

        cap.release()
