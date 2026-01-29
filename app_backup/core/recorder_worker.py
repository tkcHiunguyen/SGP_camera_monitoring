import logging
import queue
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
from app.core.motion_detector import apply_motion, ensure_motion, get_motion_config
from app.utils.paths import get_tracking_dir, get_videos_dir


class MotionClipWriter(threading.Thread):
    def __init__(self, camera_name: str, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self.camera_name = camera_name
        self.stop_event = stop_event
        self.queue: "queue.Queue[tuple[str, object] | None]" = queue.Queue(maxsize=60)
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
                            "Motion clip start: %s", self._current_path.name if self._current_path else "unknown"
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
        self, start: datetime, end: Optional[datetime] = None, suffix: str = ".ts"
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
        out_path = self._unique_path(out_dir / self._build_filename(now, suffix=".ts"))
        codec_options = ["H264", "mp2v", "mp4v"]
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
            if target.suffix == ".ts":
                self._try_remux_to_mp4(target)
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
                self.logger.info("Motion clip remuxed to %s", mp4_path.name)
                try:
                    ts_path.unlink()
                except Exception as exc:
                    self.logger.warning("Failed to delete %s: %s", ts_path.name, exc)
            else:
                self.logger.warning("ffmpeg remux failed for %s", ts_path.name)
        except Exception as exc:
            self.logger.warning("ffmpeg remux error: %s", exc)


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
        self._fps = 0.0
        self._last_fps_ts = time.time()
        self._motion_enabled = False
        self._motion_state = {"bg": None}
        self._motion_active = False
        self._motion_count = 0
        self._motion_last_seen = 0.0
        self._motion_writer: Optional[MotionClipWriter] = None
        self._motion_last_clip_ts = 0.0
        self._clip_hold_until = 0.0
        self._clip_start_ts = 0.0
        self._motion_capture_last_ts = 0.0
        self._frame_queue: "queue.Queue[cv2.Mat | None]" = queue.Queue(maxsize=8)
        self._capture_thread: Optional[threading.Thread] = None
        self._capture_stop = threading.Event()

    def get_fps(self) -> float:
        return self._fps

    def set_motion_enabled(self, enabled: bool) -> None:
        self._motion_enabled = bool(enabled)

    def get_motion_enabled(self) -> bool:
        return self._motion_enabled

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

    def _start_capture(self) -> None:
        self._capture_stop.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True
        )
        self._capture_thread.start()

    def _stop_capture(self) -> None:
        self._capture_stop.set()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2)
        self._capture_thread = None

    def _capture_loop(self) -> None:
        backoff = 0.5
        cap: Optional[cv2.VideoCapture] = None
        while not self.stop_event.is_set() and not self._capture_stop.is_set():
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                cap = self._open_capture()
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not cap.isOpened():
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 5.0)
                    continue
                backoff = 0.5
            if not cap.grab():
                time.sleep(0.02)
                cap.release()
                cap = None
                continue
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                time.sleep(0.02)
                cap.release()
                cap = None
                continue
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._frame_queue.put_nowait(frame)
                except queue.Full:
                    pass
        if cap is not None:
            cap.release()

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
        last_write = 0.0
        writer: Optional[cv2.VideoWriter] = None
        current_hour_key: Optional[str] = None
        self._current_path: Optional[Path] = None
        self._current_start: Optional[datetime] = None
        self._motion_writer = MotionClipWriter(self.camera.name, self.stop_event)
        self._motion_writer.start()
        motion_prev_active = False
        self._start_capture()

        while not self.stop_event.is_set():
            try:
                frame = self._frame_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            while True:
                try:
                    frame = self._frame_queue.get_nowait()
                except queue.Empty:
                    break
            if frame is None:
                continue

            config = get_motion_config()
            stamp = datetime.now()
            hour_key = stamp.strftime("%Y%m%d%H")
            if writer is None or hour_key != current_hour_key:
                if writer is not None:
                    writer.release()
                    self._finalize_current(stamp)
                h, w = frame.shape[:2]
                base_fps = float(config.get("record_fps", self.app_config.fps_record or 15))
                writer = self._open_writer(w, h, base_fps, stamp)
                if not writer.isOpened():
                    self.logger.error("Failed to open VideoWriter for %s", self.camera.name)
                    writer = None
                    time.sleep(0.2)
                    continue
                current_hour_key = hour_key
                self.logger.info("Recording to %s (%s)", self.camera.name, hour_key)
            if self._motion_enabled:
                ensure_motion(self._motion_state, config)
                scale = float(config.get("motion_scale", 0.5) or 0.5)
                scale = max(0.1, min(1.0, scale))
                if scale < 1.0:
                    h, w = frame.shape[:2]
                    motion_frame = cv2.resize(
                        frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA
                    )
                else:
                    motion_frame = frame
                boxes, _ = apply_motion(motion_frame, self._motion_state, config)
                if boxes and scale < 1.0:
                    inv = 1.0 / scale
                    boxes = [(int(x * inv), int(y * inv), int(w * inv), int(h * inv)) for x, y, w, h in boxes]
                now = time.time()
                start_frames = int(config.get("start_frames", 10) or 10)
                stop_seconds = float(config.get("stop_seconds", 5.0) or 5.0)
                if boxes:
                    self._motion_count += 1
                    self._motion_last_seen = now
                    if not self._motion_active and self._motion_count >= start_frames:
                        self._motion_active = True
                else:
                    self._motion_count = 0
                    if self._motion_active and (now - self._motion_last_seen) >= stop_seconds:
                        self._motion_active = False
                if self._motion_active:
                    _draw_label(frame, "MOTION", 10, 30, bg=(0, 0, 0), fg=(0, 200, 255))
                    capture_interval = float(config.get("motion_capture_seconds", 1.0) or 1.0)
                    capture_interval = max(0.1, capture_interval)
                    if now - self._motion_capture_last_ts >= capture_interval:
                        self._motion_capture_last_ts = now
                        self._save_motion_capture(frame, stamp)
                if self._motion_writer is not None:
                    stamp = datetime.now()
                    if self._motion_active and not motion_prev_active:
                        h, w = frame.shape[:2]
                        clip_fps = float(config.get("clip_fps", base_fps) or base_fps)
                        self._motion_last_clip_ts = 0.0
                        self._motion_writer.start_clip(stamp, (w, h), clip_fps)
                        self._clip_start_ts = now
                    if self._motion_active:
                        clip_fps = float(config.get("clip_fps", base_fps) or base_fps)
                        clip_fps = max(0.1, clip_fps)
                        if now - self._motion_last_clip_ts >= 1.0 / clip_fps:
                            self._motion_last_clip_ts = now
                            self._motion_writer.push_frame(frame.copy())
                        clip_hold = float(config.get("clip_hold_seconds", 2.0) or 2.0)
                        self._clip_hold_until = max(self._clip_hold_until, now + clip_hold)
                    if not self._motion_active:
                        clip_hold = float(config.get("clip_hold_seconds", 2.0) or 2.0)
                        if self._clip_hold_until == 0.0:
                            self._clip_hold_until = now + clip_hold
                        if now >= self._clip_hold_until and motion_prev_active:
                            min_clip = float(config.get("clip_min_seconds", 2.0) or 2.0)
                            if self._clip_start_ts and (now - self._clip_start_ts) < min_clip:
                                self._motion_writer.close()
                            else:
                                self._motion_writer.stop_clip(stamp)
                            self._clip_hold_until = 0.0
                            self._clip_start_ts = 0.0
                motion_prev_active = self._motion_active
            else:
                if self._motion_writer is not None and motion_prev_active:
                    self._motion_writer.stop_clip(datetime.now())
                self._motion_active = False
                self._motion_count = 0
                motion_prev_active = False
                self._clip_hold_until = 0.0
                self._clip_start_ts = 0.0
                self._motion_capture_last_ts = 0.0

            now = time.time()
            base_fps = float(config.get("record_fps", self.app_config.fps_record or 15))
            idle_fps = float(config.get("idle_record_fps", 1.0))
            if self._motion_enabled and not self._motion_active:
                target_fps = idle_fps
            else:
                target_fps = base_fps
            target_fps = max(0.1, target_fps)
            interval = 1.0 / target_fps

            if last_write == 0.0:
                last_write = now
                writer.write(frame)
            elif self._motion_enabled and self._motion_active:
                while now - last_write >= interval:
                    writer.write(frame)
                    last_write += interval
            else:
                if now - last_write < interval:
                    continue
                last_write = now
                writer.write(frame)
            now = time.time()
            delta = now - self._last_fps_ts
            if delta > 0:
                inst_fps = 1.0 / delta
                self._fps = 0.9 * self._fps + 0.1 * inst_fps
                self._last_fps_ts = now

        self._stop_capture()
        if writer is not None:
            writer.release()
            self._finalize_current(datetime.now())
        if self._motion_writer is not None:
            self._motion_writer.close()

    def _save_motion_capture(self, frame, stamp: datetime) -> None:
        capture_dir = (
            get_videos_dir()
            / f"{stamp:%Y}"
            / f"{stamp:%m}"
            / f"{stamp:%d}"
            / self.camera.name
            / "Capture"
        )
        capture_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.camera.name} motion {stamp:%d-%m-%Y %Hh%Mm%Ss}.jpg"
        path = capture_dir / filename
        cv2.imwrite(str(path), frame)


def _draw_label(frame, text, x, y, bg=(0, 0, 0), fg=(255, 255, 255)) -> None:
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    x = max(0, x)
    y = max(th + 4, y)
    cv2.rectangle(frame, (x, y - th - baseline - 4), (x + tw + 6, y + 2), bg, -1)
    cv2.putText(
        frame,
        text,
        (x + 3, y - 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        fg,
        2,
    )
