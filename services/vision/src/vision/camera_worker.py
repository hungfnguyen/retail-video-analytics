"""Single-camera processing pipeline.

Runs entirely inside a subprocess spawned by CameraManager.
Isolation guarantees that a crash in one camera does not affect others.

Pipeline (per frame):
    RTSPReader  →  Detector  →  Tracker  →  DetectionPublisher
    (thread)       (GPU)        (CPU)        (Pulsar + GCS)
"""

import logging
import multiprocessing as mp
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Configuration for a single camera (loaded from cameras.yaml)."""

    camera_id: str
    name: str
    rtsp_url: str
    store_id: str
    fps: int = 25
    location: str = ""
    enabled: bool = True


def process_camera(camera_config: CameraConfig, settings_dict: dict) -> None:
    """Entry point for a camera worker subprocess.

    This is the function passed to ``multiprocessing.Process(target=...)``.
    All imports happen inside the subprocess to avoid sharing CUDA context.

    Pipeline:
    1. Initialise logging for this subprocess.
    2. Import and construct RTSPReader — start background read thread.
    3. Import and construct Detector (YOLO11) — call warmup().
    4. Import and construct Tracker (BoTSORT).
    5. Import and construct DetectionPublisher (Pulsar + GCS).
    6. Main loop:
       a. get_frame() from RTSPReader (non-blocking; skip if no frame yet).
       b. detect() → list[Detection].
       c. tracker.update() → list[TrackedObject].
       d. publisher.publish() → async send to Pulsar, maybe upload to GCS.
    7. On SIGTERM/KeyboardInterrupt: stop reader, close publisher, exit cleanly.

    Args:
        camera_config: Camera-level settings (RTSP URL, FPS, IDs).
        settings_dict: Serialised VisionSettings fields (model path, device, etc.)
            passed as a plain dict because pydantic models are not always picklable.
    """
    # TODO: implement full pipeline loop
    raise NotImplementedError


class CameraWorker:
    """Wrapper managing a single camera's subprocess.

    Used by :class:`CameraManager` to start, stop, and monitor worker processes.
    """

    def __init__(self, config: CameraConfig, settings_dict: dict) -> None:
        self.config = config
        self._settings_dict = settings_dict
        self._process: mp.Process | None = None

    # ── Public API ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the camera worker subprocess.

        Uses ``mp.Process(target=process_camera, ...)`` with ``start_method='spawn'``
        so each subprocess gets a clean Python interpreter (no shared CUDA context).
        """
        # TODO:
        # 1. Create mp.Process(target=process_camera, args=(self.config, self._settings_dict))
        # 2. Set daemon=False (we want clean shutdown)
        # 3. process.start()
        # 4. Log PID
        raise NotImplementedError

    def stop(self, timeout: float = 5.0) -> None:
        """Gracefully stop the worker subprocess.

        Sends SIGTERM, waits up to ``timeout`` seconds, then SIGKILL.
        """
        # TODO:
        # 1. If process is None or not alive: return
        # 2. process.terminate()   (SIGTERM)
        # 3. process.join(timeout=timeout)
        # 4. If still alive: process.kill() (SIGKILL)
        raise NotImplementedError

    def is_alive(self) -> bool:
        """Return True if the subprocess is currently running."""
        # TODO: return self._process is not None and self._process.is_alive()
        raise NotImplementedError

    @property
    def pid(self) -> int | None:
        """Subprocess PID, or None if not started."""
        # TODO: return self._process.pid if self._process else None
        raise NotImplementedError
