import shutil
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


def migrate_legacy_files() -> None:
    base = get_base_dir()
    legacy_dirs = [
        base / "app" / "Files",
        base / "Files",
    ]
    new_root = get_files_dir()
    new_config = get_config_dir()
    new_log = get_log_dir()
    new_media = get_media_dir()
    new_videos = get_videos_dir()
    new_pictures = get_pictures_dir()
    new_tracking = get_tracking_dir()

    for path in [new_root, new_config, new_log, new_media, new_videos, new_pictures, new_tracking]:
        path.mkdir(parents=True, exist_ok=True)

    for legacy in legacy_dirs:
        if not legacy.exists():
            continue
        _merge_dir(legacy / "Log", new_log)
        _merge_dir(legacy / "Videos", new_videos)
        _merge_dir(legacy / "Pictures", new_pictures)
        legacy_config = legacy / "config.json"
        if legacy_config.exists() and not (new_config / "config.json").exists():
            shutil.move(str(legacy_config), str(new_config / "config.json"))


def _merge_dir(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.move(str(item), str(target))


def migrate_media_layout() -> None:
    """Reorder legacy layout to Year/Month/Day/Camera."""
    videos_root = get_videos_dir()
    pictures_root = get_pictures_dir()
    _migrate_layout_root(videos_root, ext_filter={".mp4", ".avi", ".mkv", ".ts"})
    _migrate_layout_root(pictures_root, ext_filter={".jpg", ".jpeg", ".png"})


def _migrate_layout_root(root: Path, ext_filter: set[str]) -> None:
    if not root.exists():
        return
    for cam_dir in root.iterdir():
        if not cam_dir.is_dir():
            continue
        for year_dir in cam_dir.iterdir():
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir() or not month_dir.name.isdigit():
                    continue
                for file in month_dir.rglob("*"):
                    if file.is_dir():
                        continue
                    if file.suffix.lower() not in ext_filter:
                        continue
                    day = file.stem.split(" ")[1].split("-")[0] if " " in file.stem else None
                    if not day or not day.isdigit():
                        continue
                    target_dir = root / year_dir.name / month_dir.name / day / cam_dir.name
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target = target_dir / file.name
                    if not target.exists():
                        shutil.move(str(file), str(target))
