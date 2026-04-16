import cv2
import time

def open_source(src: str):
    """Mở nguồn video hoặc RTSP."""
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise RuntimeError(f"Không mở được nguồn video: {src}")
    return cap

def get_fps(cap, fallback=25.0):
    """Lấy FPS từ video, nếu không có thì trả về mặc định."""
    fps = cap.get(cv2.CAP_PROP_FPS)
    return fps if fps and fps > 0 else fallback

def ingest_video(src, camera_id="cam_0", realtime=True, fps_hint=None):
    """Đọc từng frame từ video/RTSP, yield frame + metadata."""
    cap = open_source(src)
    fps = fps_hint or get_fps(cap)
    t0 = time.perf_counter()
    seq = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if realtime:
            due = t0 + seq / fps
            now = time.perf_counter()
            if due > now:
                time.sleep(due - now)

        yield {
            "frame": frame,
            "ts": time.time(),
            "camera_id": camera_id,
            "seq": seq,
        }
        seq += 1

    cap.release()
