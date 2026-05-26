from pathlib import Path

def get_vision_root() -> Path:
    """Return the Vision service root directory."""
    return Path(__file__).resolve().parents[1]

def resolve_model_path(model_name: str) -> Path:
    """Resolve a YOLO model file from detect/models."""
    root = get_vision_root()
    model_path = root / "detect" / "models" / model_name
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    return model_path

def resolve_tracker_config(config_name: str) -> str:
    """
    Resolve a tracker config from track/config.

    If no custom file exists, return the original config name so Ultralytics can
    use its built-in default.
    """
    root = get_vision_root()
    config_path = root / "track" / "config" / config_name
    
    if config_path.exists():
        print(f"[PathUtils] Using custom tracker config: {config_path}")
        return str(config_path)
    
    print(f"[PathUtils] Custom config '{config_name}' not found, using default.")
    return config_name
