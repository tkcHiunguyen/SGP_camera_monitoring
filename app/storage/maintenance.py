from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Iterable

from app.utils.paths import get_videos_dir


logger = logging.getLogger("StorageMaintenance")


def get_free_gb(path: Path) -> float:
    try:
        usage = shutil.disk_usage(str(path))
    except Exception:
        return 0.0
    free_bytes = usage.free
    return free_bytes / (1024 * 1024 * 1024)


def has_min_free_gb(path: Path, min_free_gb: float) -> bool:
    if min_free_gb <= 0:
        return True
    probe = path
    if not probe.exists():
        probe = probe.parent if probe.parent.exists() else probe
    free_gb = get_free_gb(probe)
    return free_gb >= min_free_gb


def prune_old_videos(days_keep: int, base_dir: Path | None = None) -> int:
    if days_keep <= 0:
        return 0
    base = base_dir or get_videos_dir()
    if not base.exists():
        return 0
    cutoff = time.time() - (days_keep * 24 * 60 * 60)
    deleted = 0
    for path in _iter_files(base):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
        except Exception as exc:
            logger.warning("Failed to delete %s: %s", path, exc)
    return deleted


def _iter_files(base: Path) -> Iterable[Path]:
    for path in base.rglob("*"):
        if path.is_file():
            yield path
