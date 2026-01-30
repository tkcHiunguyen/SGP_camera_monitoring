from pathlib import Path
from typing import Iterable, Optional

_FILES_DIR_OVERRIDE: Optional[Path] = None


def get_base_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def get_files_dir() -> Path:
    if _FILES_DIR_OVERRIDE is not None:
        return _FILES_DIR_OVERRIDE
    return get_base_dir() / "Files"


def set_files_dir(path: Path | str) -> None:
    global _FILES_DIR_OVERRIDE
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = get_base_dir() / resolved
    _FILES_DIR_OVERRIDE = resolved


def get_config_dir() -> Path:
    return get_base_dir() / "config"


def get_log_dir() -> Path:
    return get_files_dir() / "Log"


def get_media_dir() -> Path:
    return get_files_dir() / "Media"


def get_videos_dir() -> Path:
    return get_media_dir() / "Videos"


def get_pictures_dir() -> Path:
    return get_media_dir() / "Pictures"


def get_tracking_dir() -> Path:
    return get_files_dir() / "Tracking"


def get_models_dir() -> Path:
    return get_base_dir() / "models"
