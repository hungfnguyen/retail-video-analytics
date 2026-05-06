import os
from pathlib import Path
from dotenv import load_dotenv

# Define base dir (services/vision folder)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from services/vision directory
load_dotenv(BASE_DIR / ".env")

class Settings:
    # Paths
    MODEL_NAME = os.getenv("MODEL_NAME", "yolo11l.pt")
    
    # Resolve paths relative to BASE_DIR if they are not absolute
    _video_path_raw = os.getenv("VIDEO_PATH", "video/video3.mp4")
    VIDEO_PATH = str(BASE_DIR / _video_path_raw) if not Path(_video_path_raw).is_absolute() else _video_path_raw

    _out_jsonl_raw = os.getenv("OUT_JSONL", "../../data/metadata/video.jsonl")
    OUT_JSONL = str(BASE_DIR / _out_jsonl_raw) if not Path(_out_jsonl_raw).is_absolute() else _out_jsonl_raw
    
    # Tracker
    TRACKER_TYPE = os.getenv("TRACKER_TYPE", "botsort")  # botsort | bytetrack
    CONF_THRES = float(os.getenv("CONF_THRES", "0.25"))

    PULSAR_SERVICE_URL = os.getenv("PULSAR_SERVICE_URL", "pulsar://localhost:6650")
    PULSAR_TOPIC = os.getenv("PULSAR_TOPIC", "persistent://retail/metadata/events")
    
    # Filter
    # Parse string "[0, 1]" -> list [0, 1]
    _class_filter_str = os.getenv("CLASS_FILTER", "[0]")
    try:
        import json
        CLASS_FILTER = json.loads(_class_filter_str)
    except:
        CLASS_FILTER = [0]  # Default fallback

    # Metadata
    STORE_ID = os.getenv("STORE_ID", "store_01")
    CAMERA_ID = os.getenv("CAMERA_ID", "cam_01")
    STREAM_ID = os.getenv("STREAM_ID", "stream_01")

settings = Settings()
