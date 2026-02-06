import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path


logger = logging.getLogger("FFmpeg")
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

def find_ffmpeg() -> str | None:
    bundled = _find_bundled_ffmpeg()
    if bundled:
        return bundled
    return shutil.which("ffmpeg")


def _find_bundled_ffmpeg() -> str | None:
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates.append(base / exe_name)
        candidates.append(Path(sys.executable).parent / exe_name)
    else:
        base = Path(__file__).resolve().parents[2]
        candidates.append(base / exe_name)
        candidates.append(base / "bin" / exe_name)
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def remux_ts_to_mp4(
    ts_path: Path, delete_source: bool = True, transcode: bool = True
) -> Path | None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        logger.warning("ffmpeg not found; keeping %s", ts_path.name)
        return None
    mp4_path = ts_path.with_suffix(".mp4")
    if mp4_path.exists():
        return mp4_path
    if transcode:
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
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(ts_path),
            "-c",
            "copy",
            "-tag:v",
            "hvc1",
            "-bsf:a",
            "aac_adtstoasc",
            str(mp4_path),
        ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            creationflags=_CREATE_NO_WINDOW,
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
