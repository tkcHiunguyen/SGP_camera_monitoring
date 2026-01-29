from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.utils.paths import get_tracking_dir, get_videos_dir


def videos_dir_for(camera_name: str, stamp: datetime) -> Path:
    return (
        get_videos_dir()
        / f"{stamp:%Y}"
        / f"{stamp:%m}"
        / f"{stamp:%d}"
        / camera_name
    )


def motion_capture_dir_for(camera_name: str, stamp: datetime) -> Path:
    return videos_dir_for(camera_name, stamp) / "Capture"


def tracking_output_path(video_path: Path) -> Path:
    try:
        rel = video_path.relative_to(get_videos_dir())
    except ValueError:
        rel = Path(video_path.name)
    return get_tracking_dir() / rel
