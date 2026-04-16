# analytics/json_emitter.py
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

class JsonEmitter:
    def __init__(self, outfile: str, schema_version: str = "1.0"):
        self.outfile = outfile
        self.schema_version = schema_version
        
        # Tạo thư mục nếu chưa có
        Path(outfile).parent.mkdir(parents=True, exist_ok=True)
        
        self._f = open(self.outfile, "a", buffering=1, encoding="utf-8")  # line-buffered

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

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
    ):
        record = {
            "schema_version": self.schema_version,
            "pipeline_run_id": pipeline_run_id,
            "source": source,
            "frame_index": frame_index,
            "capture_ts": capture_ts_iso or self._now_iso(),
            "image_size": image_size,
            "detections": detections,
        }
        if runtime:     record["runtime"] = runtime
        if source_uri:  record["source_uri"] = source_uri
        self._f.write(json.dumps(record, ensure_ascii=False) + "\n")
