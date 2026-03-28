#!/usr/bin/env python3
"""Download YOLO model weights to data/models/."""

import os
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "data" / "models"

AVAILABLE_MODELS = {
    "yolo11n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
    "yolo11s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt",
    "yolo11m.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt",
    "yolo11l.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11l.pt",
    "yolo11x.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x.pt",
}


def download(model_name: str) -> None:
    import urllib.request

    if model_name not in AVAILABLE_MODELS:
        print(f"Unknown model: {model_name}. Available: {list(AVAILABLE_MODELS)}")
        sys.exit(1)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / model_name

    if dest.exists():
        print(f"{model_name} already exists at {dest}")
        return

    url = AVAILABLE_MODELS[model_name]
    print(f"Downloading {model_name} from {url}...")
    urllib.request.urlretrieve(url, dest)
    print(f"Saved to {dest}")


if __name__ == "__main__":
    model = os.getenv("MODEL_NAME", "yolo11l.pt")
    if len(sys.argv) > 1:
        model = sys.argv[1]
    download(model)
