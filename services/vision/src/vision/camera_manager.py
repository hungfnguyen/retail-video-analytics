"""Camera manager — supervisor for all camera worker processes.

Responsibilities:
- Parse cameras.yaml and build CameraConfig objects.
- Spawn one CameraWorker subprocess per enabled camera.
- Run a health-check loop every 10 seconds.
- Auto-restart dead workers.
- Handle SIGTERM / SIGINT for graceful shutdown.

Typical flow::

    manager = CameraManager()
    manager.run()   # blocks; handles signals internally
"""

import logging
import signal
import time
from pathlib import Path

import yaml

from vision.camera_worker import CameraConfig, CameraWorker
from vision.config import VisionSettings

logger = logging.getLogger(__name__)


class CameraManager:
    """Supervisor that orchestrates multiple :class:`CameraWorker` subprocesses.

    Args:
        config_path: Path to ``cameras.yaml``.  Resolved relative to CWD if relative.
        settings: Optional pre-built :class:`VisionSettings`.  Loaded from env if None.
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        settings: VisionSettings | None = None,
    ) -> None:
        self._settings = settings or VisionSettings()  # type: ignore[call-arg]
        self._config_path = Path(config_path or self._settings.cameras_config_path)
        self._cameras: list[CameraConfig] = []
        self._workers: dict[str, CameraWorker] = {}   # camera_id → worker
        self._running = False

    # ── Public API ──────────────────────────────────────────────────────────

    def load_configs(self) -> list[CameraConfig]:
        """Parse cameras.yaml and return enabled CameraConfig objects.

        Returns:
            List of :class:`CameraConfig` where ``enabled=True``.

        Raises:
            FileNotFoundError: If config_path does not exist.
            yaml.YAMLError: On YAML parse failure.
        """
        # TODO:
        # 1. yaml.safe_load(config_path.read_text())
        # 2. Build CameraConfig for each entry where enabled=True
        # 3. Assign to self._cameras and return
        raise NotImplementedError

    def start_all(self) -> None:
        """Spawn one CameraWorker subprocess per enabled camera.

        Calls load_configs() internally if self._cameras is empty.
        """
        # TODO:
        # 1. load_configs() if needed
        # 2. For each CameraConfig: create CameraWorker, call worker.start()
        # 3. Populate self._workers dict
        raise NotImplementedError

    def stop_all(self) -> None:
        """Stop all running workers gracefully."""
        # TODO: call worker.stop() for each worker in self._workers
        raise NotImplementedError

    def health_check(self) -> dict[str, bool]:
        """Return liveness status for all managed cameras.

        Returns:
            Dict mapping camera_id → is_alive (bool).
        """
        # TODO: {cid: w.is_alive() for cid, w in self._workers.items()}
        raise NotImplementedError

    def restart_dead_workers(self) -> list[str]:
        """Detect and respawn workers that have exited unexpectedly.

        Returns:
            List of camera_ids that were restarted in this call.
        """
        # TODO:
        # 1. For each worker where not is_alive(): log warning, call worker.start()
        # 2. Return list of restarted camera_ids
        raise NotImplementedError

    def run(self) -> None:
        """Block and supervise workers until shutdown signal.

        Loop:
        1. Register SIGTERM + SIGINT handlers via _handle_signal.
        2. start_all() to spawn workers.
        3. Every health_check_interval seconds: call health_check(),
           then restart_dead_workers().
        4. On signal: stop_all() and return.
        """
        # TODO: implement main supervision loop
        raise NotImplementedError

    # ── Private ─────────────────────────────────────────────────────────────

    def _handle_signal(self, signum: int, frame) -> None:
        """Signal handler — triggers graceful shutdown.

        Sets self._running = False so the run() loop exits on next iteration.
        """
        # TODO: log signal received, set self._running = False
        raise NotImplementedError
