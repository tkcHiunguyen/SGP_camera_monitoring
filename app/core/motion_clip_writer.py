import logging
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

from app.utils.paths import get_tracking_dir


class MotionClipWriter(threading.Thread):
    def __init__(self, camera_name: str, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self.camera_name = camera_name
        self.stop_event = stop_event
        self.queue: "queue.Queue[tuple[str, object] | None]" = queue.Queue(maxsize=300)
        self._writer: Optional[cv2.VideoWriter] = None
        self._current_path: Optional[Path] = None
        self._current_start: Optional[datetime] = None
        self.logger = logging.getLogger(f"MotionClip[{camera_name}]")

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            cmd, payload = item
            if cmd == "start":
                stamp, frame_size, fps = payload
                if self._writer is None:
                    self._writer = self._open_writer(
                        frame_size[0], frame_size[1], fps, stamp
                    )
                    if self._writer is not None and self._writer.isOpened():
                        self.logger.info(
                            "Motion clip start: %s",
                            self._current_path.name if self._current_path else "unknown",
                        )
            elif cmd == "frame":
                if self._writer is not None:
                    self._writer.write(payload)
            elif cmd == "stop":
                end = payload
                self._finalize_current(end)
        self._finalize_current(datetime.now())

    def start_clip(self, stamp: datetime, frame_size: tuple[int, int], fps: float) -> None:
        self._put(("start", (stamp, frame_size, fps)))

    def push_frame(self, frame) -> None:
        self._put(("frame", frame))

    def stop_clip(self, stamp: datetime) -> None:
        self._put(("stop", stamp))

    def close(self) -> None:
        self._put(None)

    def _put(self, item) -> None:
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            pass

    def _build_output_dir(self, now: datetime) -> Path:
        return (
            get_tracking_dir()
            / f"{now:%Y}"
            / f"{now:%m}"
            / f"{now:%d}"
            / self.camera_name
        )

    def _build_filename(
        self, start: datetime, end: Optional[datetime] = None, suffix: str = ".mp4"
    ) -> str:
        if end is None:
            return f"{self.camera_name} motion {start:%d-%m-%Y %Hh%Mm%Ss}{suffix}"
        return (
            f"{self.camera_name} motion {start:%d-%m-%Y %Hh%Mm%Ss} - "
            f"{end:%d-%m-%Y %Hh%Mm%Ss}{suffix}"
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
        out_dir = self._build_output_dir(now)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._unique_path(out_dir / self._build_filename(now, suffix=".mp4"))
        codec_options = ["mp4v"]
        fps = max(0.1, fps)
        for codec in codec_options:
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = self._try_open_writer(out_path, fourcc, fps, frame_width, frame_height)
            if writer is not None and writer.isOpened():
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
            return cv2.VideoWriter(str(out_path), fourcc, fps, (frame_width, frame_height))

    def _finalize_current(self, end: datetime) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        if not self._current_path or not self._current_start:
            return
        try:
            target = self._current_path.with_name(
                self._build_filename(self._current_start, end, suffix=self._current_path.suffix)
            )
            target = self._unique_path(target)
            if self._current_path.exists():
                self._current_path.rename(target)
            self.logger.info("Motion clip saved: %s", target.name)
            # mp4v writer already outputs mp4
        finally:
            self._current_path = None
            self._current_start = None
