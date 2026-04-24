from pathlib import Path
import os

def get_project_root() -> Path:
    """Return the project root directory."""
    # This file lives in vision/utils, so the repository root is two levels up.
    return Path(__file__).resolve().parents[2]

def resolve_model_path(model_name: str) -> Path:
    """
    Tìm file model trong detect/models/.
    """
    root = get_project_root()
    model_path = root / "detect" / "models" / model_name
    if not model_path.exists():
        raise FileNotFoundError(f"Không tìm thấy model: {model_path}")
    return model_path

def resolve_tracker_config(config_name: str) -> str:
    """
    Tìm file config tracker trong track/config/.
    Nếu không thấy, trả về tên gốc để Ultralytics tự xử lý (default).
    """
    root = get_project_root()
    config_path = root / "track" / "config" / config_name
    
    if config_path.exists():
        print(f"[PathUtils] Sử dụng config tracker custom: {config_path}")
        return str(config_path)
    
    print(f"[PathUtils] Không tìm thấy config custom '{config_name}', dùng mặc định.")
    return config_name
