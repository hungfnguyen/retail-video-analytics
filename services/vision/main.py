# services/vision/main.py — CameraManager entry point
import signal
import sys
import time
import logging
from multiprocessing import Process

from config.settings import load_cameras_config
from worker import run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [manager] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_workers: dict[str, Process] = {}
_running = True
_global_cfg = {}


def _shutdown(signum, frame):
    global _running
    logger.info("Received signal %s, shutting down...", signum)
    _running = False


def _start_worker(worker_id: str) -> Process:
    camera_cfg = _global_cfg["cameras"][worker_id]
    logger.info("Starting worker: %s (%s)", camera_cfg["camera_id"], camera_cfg["source_uri"])
    p = Process(target=run_worker, args=(camera_cfg, _global_cfg), name=camera_cfg["camera_id"])
    p.start()
    return p


def _restart_worker(worker_id: str, restart_count: dict[str, int]) -> Process | None:
    camera_cfg = _global_cfg["cameras"][worker_id]
    restart_count[worker_id] = restart_count.get(worker_id, 0) + 1
    backoff = min(2 ** (restart_count[worker_id] - 1), 30)
    logger.warning(
        "Worker %s died, restarting in %ds (attempt #%d)...",
        camera_cfg["camera_id"], backoff, restart_count[worker_id],
    )
    time.sleep(backoff)
    return _start_worker(worker_id)


def main():
    global _global_cfg

    # Load config
    cfg = load_cameras_config()
    _global_cfg = cfg
    cameras_list = cfg["cameras"]

    if not cameras_list:
        logger.error("No cameras configured. Check configs/cameras.yaml or .env")
        sys.exit(1)

    logger.info("Loaded %d cameras", len(cameras_list))
    for c in cameras_list:
        logger.info("  %s: %s (%s) → %s", c["camera_id"], c.get("name", ""), c["source_type"], c["source_uri"])
    logger.info("Pulsar: %s [%s]", cfg["pulsar_service_url"], cfg["pulsar_topic"])
    logger.info("Model: %s, Tracker: %s, Queue: %d, Conf: %.2f",
                cfg["model_name"], cfg["tracker_type"], cfg["frame_queue_size"], cfg["conf_thres"])

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Start all workers
    restart_count: dict[str, int] = {}
    for worker_id, _ in enumerate(cameras_list):
        _workers[worker_id] = _start_worker(worker_id)

    # Health check loop
    health_interval = cfg.get("health_check_interval_sec", 10)
    while _running:
        time.sleep(health_interval)
        if not _running:          # shutdown signal received during sleep
            break

        for worker_id, p in list(_workers.items()):
            if not p.is_alive():
                if p.exitcode != 0:
                    logger.error("Worker %s (pid=%d) exit code=%d",
                                 _workers[worker_id].name, p.pid, p.exitcode)
                if not _running:   # shutting down — don't restart
                    break
                new_p = _restart_worker(worker_id, restart_count)
                if new_p:
                    _workers[worker_id] = new_p

    # Graceful shutdown
    logger.info("Stopping all workers (graceful timeout=%ds)...",
                cfg.get("worker_graceful_shutdown_sec", 10))
    for worker_id, p in _workers.items():
        if p.is_alive():
            p.terminate()
    for worker_id, p in _workers.items():
        p.join(timeout=cfg.get("worker_graceful_shutdown_sec", 10))
        if p.is_alive():
            logger.warning("Worker %s did not stop, force killing", worker_id)
            p.kill()

    logger.info("All workers stopped. Exiting.")


if __name__ == "__main__":
    main()
