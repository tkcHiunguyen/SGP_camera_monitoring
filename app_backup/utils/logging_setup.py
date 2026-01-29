import logging
from logging.handlers import RotatingFileHandler

from app.utils.paths import get_log_dir, get_videos_dir


def ensure_dirs() -> None:
    get_log_dir().mkdir(parents=True, exist_ok=True)
    get_videos_dir().mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    ensure_dirs()
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    log_path = get_log_dir() / "app.log"
    handler = RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
