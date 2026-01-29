from pathlib import Path
from typing import Iterable


def get_base_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def get_files_dir() -> Path:
    return get_base_dir() / "Files"


def get_config_dir() -> Path:
    return get_files_dir() / "Config"


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
