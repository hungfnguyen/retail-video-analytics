import cv2
import numpy as np
from typing import Dict, List, Any, Tuple

class Visualizer:
    """
    Class chuyên trách việc vẽ bounding box, label và thông tin lên frame.
    """
    def __init__(self, font_scale: float = 0.45, thickness: int = 1):
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.font_scale = font_scale
        self.thickness = thickness
        self.bbox_color = (255, 191, 0)  # Lightblue (BGR)
        self.text_color = (0, 0, 0)      # Black

    def draw_tracks(self, frame: np.ndarray, tracks: List[Dict[str, Any]]) -> np.ndarray:
        """
        Vẽ danh sách các object được track lên frame.
        
        Args:
            frame: Ảnh gốc (BGR).
            tracks: Danh sách object từ tracker (có bbox, label, id, conf).
            
        Returns:
            Frame đã được vẽ (copy hoặc inplace tùy implementation, ở đây là inplace).
        """
        for obj in tracks:
            bbox = obj.get("bbox")
            if not bbox:
                continue
                
            x1, y1, x2, y2 = map(int, bbox)
            label_text = obj.get("label", "unknown")
            track_id = obj.get("id", -1)
            conf = obj.get("conf", 0.0)
            
            display_text = f"{label_text} ID:{track_id} {conf:.2f}"
            
            self._draw_box_and_label(frame, (x1, y1, x2, y2), display_text)
            
        return frame

    def _draw_box_and_label(self, frame: np.ndarray, bbox: Tuple[int, int, int, int], text: str):
        x1, y1, x2, y2 = bbox
        
        # Vẽ bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), self.bbox_color, 2)
        
        # Tính kích thước text
        (text_w, text_h), baseline = cv2.getTextSize(text, self.font, self.font_scale, self.thickness)
        
        # Vẽ background cho text
        cv2.rectangle(frame, 
                     (x1, y1 - text_h - baseline - 5),
                     (x1 + text_w, y1),
                     self.bbox_color, -1)
        
        # Vẽ text
        cv2.putText(frame, text, (x1, y1 - baseline - 2),
                   self.font, self.font_scale, self.text_color, self.thickness)
