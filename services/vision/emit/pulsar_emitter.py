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
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        
        try:
            # Use listener_name='external' to connect via localhost when running from host
            self.client = pulsar.Client(service_url, listener_name='external')
            self.producer = self.client.create_producer(topic)
            logger.info(f"Successfully connected to topic '{topic}'")
        except Exception as e:
            logger.error(f"Failed to connect to Pulsar: {e}", exc_info=True)
            raise

    def close(self):
        """Đóng kết nối Pulsar một cách an toàn."""
        try:
            self.producer.close()
            self.client.close()
            logger.info("Pulsar connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing Pulsar connection: {e}", exc_info=True)

    @staticmethod
    def _now_iso() -> str:
        """Trả về timestamp ISO format hiện tại (UTC)."""
        return datetime.now(timezone.utc).isoformat()

    def _send_with_retry(self, payload: bytes, frame_index: int) -> bool:
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
                self.producer.send(payload)
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
                            "topic": self.topic
                        }
                    )
                    return False
        
        return False

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
