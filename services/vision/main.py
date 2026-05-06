# services/vision/main.py

import uuid
import cv2
import logging
from datetime import datetime, timezone

from track.tracker_factory import create_tracker
from utils.visualizer import Visualizer
from config.settings import settings
from emit.pulsar_emitter import PulsarEmitter


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    pipeline_run_id = uuid.uuid4().hex

    source = {
        "store_id": settings.STORE_ID,
        "camera_id": settings.CAMERA_ID,
        "stream_id": settings.STREAM_ID,
    }

    pulsar_url = settings.PULSAR_SERVICE_URL
    pulsar_topic = settings.PULSAR_TOPIC

    logger.info("Starting pipeline run: %s", pipeline_run_id)
    logger.info("Config: Model=%s, Tracker=%s", settings.MODEL_NAME, settings.TRACKER_TYPE)
    logger.info("Ingestion: Pulsar (%s) topic=%s", pulsar_url, pulsar_topic)

    tracker = None
    emitter = None

    try:
        tracker = create_tracker(settings.TRACKER_TYPE, settings.MODEL_NAME, conf_thres=settings.CONF_THRES)

        try:
            emitter = PulsarEmitter(pulsar_url, pulsar_topic)
        except Exception as e:
            logger.error("Cannot connect to Pulsar: %s", e)
            logger.info("Hint: ensure docker compose is running and the Pulsar port is reachable from host.")
            raise SystemExit(1)

        visualizer = Visualizer()

        track_stream = tracker.track(settings.VIDEO_PATH, show=False, classes=settings.CLASS_FILTER)

        for idx, record in enumerate(track_stream, start=1):
            frame = record["frame"]
            height, width = frame.shape[:2]
            objects = record["objects"]

            visualizer.draw_tracks(frame, objects)

            detections = []
            for j, obj in enumerate(objects):
                x1, y1, x2, y2 = map(float, obj["bbox"])
                w_box = x2 - x1
                h_box = y2 - y1
                cx = x1 + w_box / 2.0
                cy = y1 + h_box / 2.0

                detections.append(
                    {
                        "det_id": f"{idx}-{j}",
                        "class": obj.get("label", "person"),
                        "class_id": int(obj.get("cls", 0)),
                        "conf": float(obj.get("conf", 0.0)),
                        "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                        "bbox_norm": {"x": x1 / width, "y": y1 / height, "w": w_box / width, "h": h_box / height},
                        "centroid": {"x": int(cx), "y": int(cy)},
                        "centroid_norm": {"x": cx / width, "y": cy / height},
                        "track_id": None if obj.get("id", -1) < 0 else int(obj["id"]),
                    }
                )

            success = emitter.emit_frame(
                pipeline_run_id=pipeline_run_id,
                source=source,
                frame_index=idx,
                capture_ts_iso=datetime.now(timezone.utc).isoformat(),
                image_size={"width": width, "height": height},
                detections=detections,
                runtime={
                    "model_name": settings.MODEL_NAME,
                    "tracker_type": settings.TRACKER_TYPE,
                },
            )

            if not success:
                logger.warning("Failed to emit frame %s", idx)

            cv2.imshow("Retail Analytics", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                logger.info("Stop signal received from user")
                break

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user (Ctrl+C)")
    except Exception as e:
        logger.error("Unexpected error in pipeline: %s", e, exc_info=True)
    finally:
        logger.info("Cleaning up resources...")

        if emitter is not None:
            try:
                emitter.close()
            except Exception as e:
                logger.error("Error closing emitter: %s", e)

        try:
            cv2.destroyAllWindows()
        except Exception as e:
            logger.error("Error destroying OpenCV windows: %s", e)

        logger.info("Pipeline stopped")
