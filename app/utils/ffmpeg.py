import logging
import shutil
import subprocess
from pathlib import Path


logger = logging.getLogger("FFmpeg")


def remux_ts_to_mp4(ts_path: Path, delete_source: bool = True) -> Path | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("ffmpeg not found; keeping %s", ts_path.name)
        return None
    mp4_path = ts_path.with_suffix(".mp4")
    if mp4_path.exists():
        return mp4_path
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(ts_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(mp4_path),
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
        if result.returncode == 0 and mp4_path.exists():
            logger.info("Remuxed to %s", mp4_path.name)
            if delete_source:
                try:
                    ts_path.unlink()
                except Exception as exc:
                    logger.warning("Failed to delete %s: %s", ts_path.name, exc)
            return mp4_path
        logger.warning("ffmpeg remux failed for %s", ts_path.name)
        return None
    except Exception:
        logger.exception("ffmpeg remux error for %s", ts_path.name)
        return None
