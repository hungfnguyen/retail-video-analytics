# services/vision/emit/pulsar_emitter.py
import json
import logging
import time
import pulsar
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PulsarEmitter:
    def __init__(
        self, 
        service_url: str, 
        topic: str,
        media_topic: Optional[str] = None,
        max_retries: int = 3,
        initial_backoff: float = 0.5
    ):
        """
        Khởi tạo PulsarEmitter với retry logic.
        
        Args:
            service_url: URL của Pulsar service
            topic: Topic để publish messages
            max_retries: Số lần retry tối đa khi send thất bại
            initial_backoff: Thời gian chờ ban đầu (giây) cho exponential backoff
        """
        logger.info(f"Connecting to Pulsar at {service_url}...")
        self.service_url = service_url
        self.topic = topic
        self.media_topic = media_topic
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.media_producer = None
        
        try:
            # Use listener_name='external' to connect via localhost when running from host
            self.client = pulsar.Client(service_url, listener_name='external')
            self.producer = self.client.create_producer(topic)
            logger.info(f"Successfully connected to topic '{topic}'")
            if media_topic:
                try:
                    self.media_producer = self.client.create_producer(media_topic)
                    logger.info(f"Successfully connected to media topic '{media_topic}'")
                except Exception:
                    logger.warning(
                        "Cannot create media producer for topic '%s'; media events will be skipped",
                        media_topic,
                        exc_info=True,
                    )
        except Exception as e:
            logger.error(f"Failed to connect to Pulsar: {e}", exc_info=True)
            raise

    def close(self):
        """Đóng kết nối Pulsar một cách an toàn."""
        try:
            if self.media_producer:
                self.media_producer.close()
            self.producer.close()
            self.client.close()
            logger.info("Pulsar connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing Pulsar connection: {e}", exc_info=True)

    @staticmethod
    def _now_iso() -> str:
        """Trả về timestamp ISO format hiện tại (UTC)."""
        return datetime.now(timezone.utc).isoformat()

    def _send_payload_with_retry(
        self,
        producer: Any,
        payload: bytes,
        frame_index: int,
        topic: str,
    ) -> bool:
        """
        Gửi message với exponential backoff retry.
        
        Args:
            payload: Dữ liệu JSON đã encode
            frame_index: Frame index để logging
            
        Returns:
            True nếu gửi thành công, False nếu thất bại sau tất cả retries
        """
        for attempt in range(self.max_retries):
            try:
                producer.send(payload)
                return True
            except Exception as e:
                backoff_time = self.initial_backoff * (2 ** attempt)
                
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Failed to send frame {frame_index} (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {backoff_time:.2f}s..."
                    )
                    time.sleep(backoff_time)
                else:
                    logger.error(
                        f"Failed to send frame {frame_index} after {self.max_retries} attempts: {e}",
                        exc_info=True,
                        extra={
                            "frame_index": frame_index,
                            "error_type": type(e).__name__,
                            "topic": topic
                        }
                    )
                    return False
        
        return False

    def _send_with_retry(self, payload: bytes, frame_index: int) -> bool:
        return self._send_payload_with_retry(self.producer, payload, frame_index, self.topic)

    def emit_frame(
        self,
        *,
        pipeline_run_id: str,
        source: Dict[str, Any],
        frame_index: int,
        capture_ts_iso: Optional[str],
        image_size: Dict[str, int],
        detections: List[Dict[str, Any]],
        runtime: Optional[Dict[str, Any]] = None,
        source_uri: Optional[str] = None
    ) -> bool:
        """
        Gửi frame metadata lên Pulsar topic.
        
        Args:
            pipeline_run_id: ID duy nhất của pipeline run
            source: Thông tin nguồn (store_id, camera_id, stream_id)
            frame_index: Chỉ số frame
            capture_ts_iso: Timestamp capture (ISO format)
            image_size: Kích thước ảnh (width, height)
            detections: Danh sách các detections trong frame
            runtime: Thông tin runtime (model_name, tracker_type, etc.)
            source_uri: URI nguồn video (optional)
            
        Returns:
            True nếu gửi thành công, False nếu thất bại
        """
        # 1. Tạo bản ghi metadata
        record = {
            "schema_version": "1.0",
            "pipeline_run_id": pipeline_run_id,
            "source": source,
            "frame_index": frame_index,
            "capture_ts": capture_ts_iso or self._now_iso(),
            "image_size": image_size,
            "detections": detections,
        }
        if runtime:
            record["runtime"] = runtime
        if source_uri:
            record["source_uri"] = source_uri
        
        # 2. Serialize và gửi lên Pulsar với retry
        try:
            json_str = json.dumps(record, ensure_ascii=False)
            payload = json_str.encode('utf-8')
            
            success = self._send_with_retry(payload, frame_index)
            
            # Log nhẹ để theo dõi tiến trình (mỗi 30 frames)
            if success and frame_index % 30 == 0:
                logger.info(
                    f"Successfully sent frame {frame_index}",
                    extra={
                        "frame_index": frame_index,
                        "detections_count": len(detections),
                        "pipeline_run_id": pipeline_run_id
                    }
                )
            
            return success
            
        except Exception as e:
            logger.error(
                f"Unexpected error while preparing frame {frame_index}: {e}",
                exc_info=True,
                extra={
                    "frame_index": frame_index,
                    "error_type": type(e).__name__
                }
            )
            return False

    def emit_media_event(self, record: Dict[str, Any], frame_index: Optional[int] = None) -> bool:
        """Publish media artifact event to the optional media topic."""
        if not self.media_producer or not self.media_topic:
            return False

        try:
            json_str = json.dumps(record, ensure_ascii=False)
            payload = json_str.encode("utf-8")
            idx = frame_index
            if idx is None:
                raw_idx = record.get("frame_index") or record.get("trigger_frame_index") or -1
                try:
                    idx = int(raw_idx)
                except Exception:
                    idx = -1

            success = self._send_payload_with_retry(self.media_producer, payload, idx, self.media_topic)
            if success:
                logger.info(
                    "Published media event type=%s frame=%s",
                    record.get("event_type"),
                    idx,
                )
            return success
        except Exception:
            logger.exception("Unexpected error while preparing media event")
            return False
