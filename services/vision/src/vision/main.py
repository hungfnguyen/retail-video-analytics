"""Vision service entry point.

Starts the CameraManager which spawns one subprocess per camera.

Usage::

    uv run rva-vision
    # or
    python -m vision.main
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Entry point for the ``rva-vision`` CLI command."""
    from vision.camera_manager import CameraManager

    logger.info("Starting RVA Vision Service")

    manager = CameraManager()

    try:
        manager.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        manager.stop_all()
        logger.info("Vision service stopped")


if __name__ == "__main__":
    main()
