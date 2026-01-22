import logging
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from urllib.parse import quote

import cv2

from app.config.models import AppConfig, CameraConfig
from app.utils.paths import get_videos_dir


class RecorderWorker(threading.Thread):
    def __init__(
        self,
        camera: CameraConfig,
        app_config: AppConfig,
        stop_event: threading.Event,
        tracking_manager=None,
    ) -> None:
        super().__init__(daemon=True)
        self.camera = camera
        self.app_config = app_config
        self.stop_event = stop_event
        self.tracking_manager = tracking_manager
        self.logger = logging.getLogger(f"Recorder[{camera.name}]")

    def _build_rtsp_url(self) -> str:
        if self.camera.rtsp_url:
            return self.camera.rtsp_url
        user = quote(self.camera.user, safe="")
        password = quote(self.camera.password, safe="")
        auth = f"{user}:{password}@" if user or password else ""
        return f"rtsp://{auth}{self.camera.ip}:{self.camera.port}{self.camera.stream_path}"

    def _open_capture(self) -> cv2.VideoCapture:
        if self.camera.source == "device":
            return cv2.VideoCapture(self.camera.device_index)
        return cv2.VideoCapture(self._build_rtsp_url(), cv2.CAP_FFMPEG)

    def _build_output_path(self, now: datetime, suffix: str) -> Path:
        base = self._build_output_dir(now)
        filename = self._build_filename(now, suffix=suffix)
        return self._unique_path(base / filename)

    def _build_output_dir(self, now: datetime) -> Path:
        return (
            get_videos_dir()
            / f"{now:%Y}"
            / f"{now:%m}"
            / f"{now:%d}"
            / self.camera.name
        )

    def _build_filename(
        self, start: datetime, end: Optional[datetime] = None, suffix: str = ".mkv"
    ) -> str:
        if end is None:
            return (
                f"{self.camera.name} {self.camera.mode} "
                f"{start:%d-%m-%Y %Hh%Mm%Ss}{suffix}"
            )
        return (
            f"{self.camera.name} {self.camera.mode} "
            f"{start:%d-%m-%Y %Hh%Mm%Ss} - {end:%d-%m-%Y %Hh%Mm%Ss}{suffix}"
        )

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        for idx in range(1, 1000):
            candidate = path.with_name(f"{stem} ({idx}){suffix}")
            if not candidate.exists():
                return candidate
        return path

    def _open_writer(
        self, frame_width: int, frame_height: int, fps: float, now: datetime
    ) -> cv2.VideoWriter:
        self._build_output_dir(now).mkdir(parents=True, exist_ok=True)
        codec_options = [
            ("mp2v", ".ts"),
            ("H264", ".ts"),
            ("mp4v", ".mp4"),
            ("XVID", ".avi"),
            ("MJPG", ".avi"),
        ]
        for codec, suffix in codec_options:
            out_path = self._build_output_path(now, suffix)
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = self._try_open_writer(out_path, fourcc, fps, frame_width, frame_height)
            if writer is not None and writer.isOpened():
                self.logger.info("VideoWriter codec: %s (%s)", codec, out_path.suffix)
                self._current_path = out_path
                self._current_start = now
                return writer
        return cv2.VideoWriter()

    def _try_open_writer(
        self,
        out_path: Path,
        fourcc: int,
        fps: float,
        frame_width: int,
        frame_height: int,
    ) -> Optional[cv2.VideoWriter]:
        try:
            return cv2.VideoWriter(
                str(out_path),
                cv2.CAP_FFMPEG,
                fourcc,
                fps,
                (frame_width, frame_height),
            )
        except TypeError:
            return cv2.VideoWriter(
                str(out_path), fourcc, fps, (frame_width, frame_height)
            )

    def _finalize_current(self, end: datetime) -> None:
        if not self._current_path or not self._current_start:
            return
        try:
            base_dir = self._build_output_dir(self._current_start)
            base_dir.mkdir(parents=True, exist_ok=True)
            target = base_dir / self._build_filename(
                self._current_start, end, suffix=self._current_path.suffix
            )
            target = self._unique_path(target)
            if self._current_path.exists():
                self._current_path.rename(target)
            if target.suffix == ".ts":
                self._try_remux_to_mp4(target)
        except Exception as exc:
            self.logger.warning("Failed to finalize filename: %s", exc)
        finally:
            self._current_path = None
            self._current_start = None

    def _try_remux_to_mp4(self, ts_path: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.logger.warning("ffmpeg not found; keeping %s", ts_path.name)
            return
        mp4_path = ts_path.with_suffix(".mp4")
        if mp4_path.exists():
            return
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(ts_path),
            "-c",
            "copy",
            str(mp4_path),
        ]
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
            )
            if result.returncode == 0 and mp4_path.exists():
                self.logger.info("Remuxed to %s", mp4_path.name)
                try:
                    ts_path.unlink()
                except Exception as exc:
                    self.logger.warning("Failed to delete %s: %s", ts_path.name, exc)
                if self.tracking_manager is not None:
                    self.tracking_manager.enqueue(mp4_path)
            else:
                self.logger.warning("ffmpeg remux failed for %s", ts_path.name)
        except Exception as exc:
            self.logger.warning("ffmpeg remux error: %s", exc)

    def run(self) -> None:
        cap = self._open_capture()
        if not cap.isOpened():
            self.logger.error("Failed to open capture")
            return

        fps = float(self.app_config.fps_record or 15)
        last_write = 0.0
        writer: Optional[cv2.VideoWriter] = None
        current_hour_key: Optional[str] = None
        self._current_path: Optional[Path] = None
        self._current_start: Optional[datetime] = None

        while not self.stop_event.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            now = time.time()
            if now - last_write < 1.0 / fps:
                continue
            last_write = now

            stamp = datetime.now()
            hour_key = stamp.strftime("%Y%m%d%H")
            if writer is None or hour_key != current_hour_key:
                if writer is not None:
                    writer.release()
                    self._finalize_current(stamp)
                h, w = frame.shape[:2]
                writer = self._open_writer(w, h, fps, stamp)
                if not writer.isOpened():
                    self.logger.error("Failed to open VideoWriter for %s", self.camera.name)
                    writer = None
                    time.sleep(0.2)
                    continue
                current_hour_key = hour_key
                self.logger.info("Recording to %s (%s)", self.camera.name, hour_key)

            writer.write(frame)

        cap.release()
        if writer is not None:
            writer.release()
            self._finalize_current(datetime.now())
