from pathlib import Path


def get_vision_root() -> Path:
    """Return the Vision service root directory."""
    return Path(__file__).resolve().parents[1]


def resolve_model_path(model_name: str) -> Path:
    """Resolve a detector model file from services/vision/detect/models."""
    root = get_vision_root()
    model_path = root / "detect" / "models" / model_name
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    return model_path
