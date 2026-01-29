import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Callable

import cv2

from app.config.models import AppConfig, CameraConfig
from app.core.motion_clip_writer import MotionClipWriter
from app.core.motion_detector import apply_motion, ensure_motion, get_motion_config
from app.storage.layout import motion_capture_dir_for, videos_dir_for
from app.storage.maintenance import get_free_gb, has_min_free_gb
from app.utils.ffmpeg import remux_ts_to_mp4
from app.utils.paths import get_videos_dir
from app.utils.rtsp import build_rtsp_url


class RecorderWorker(threading.Thread):
    def __init__(
        self,
        camera: CameraConfig,
        app_config: AppConfig,
        stop_event: threading.Event,
        tracking_manager=None,
        disk_warning_cb: Optional[Callable[[float, float], None]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.camera = camera
        self.app_config = app_config
        self.stop_event = stop_event
        self.tracking_manager = tracking_manager
        self.disk_warning_cb = disk_warning_cb
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
        self._disk_low_last_log = 0.0
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
        return build_rtsp_url(self.camera)

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
        return videos_dir_for(self.camera.name, now)

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
        mp4_path = remux_ts_to_mp4(ts_path, delete_source=True)
        if mp4_path is not None and self.tracking_manager is not None:
            self.tracking_manager.enqueue(mp4_path)

    def _next_frame(self) -> Optional[cv2.Mat]:
        try:
            frame = self._frame_queue.get(timeout=0.2)
        except queue.Empty:
            return None
        while True:
            try:
                frame = self._frame_queue.get_nowait()
            except queue.Empty:
                break
        return frame

    def _ensure_writer(
        self,
        frame,
        stamp: datetime,
        writer: Optional[cv2.VideoWriter],
        hour_key: Optional[str],
        config: dict,
    ) -> tuple[Optional[cv2.VideoWriter], Optional[str], float]:
        if self.app_config.enable_disk_check:
            free_gb = get_free_gb(get_videos_dir())
            if free_gb < float(self.app_config.min_free_gb):
                now = time.time()
                if now - self._disk_low_last_log > 10.0:
                    self.logger.warning(
                        "Disk free %.2f GB below %s GB for %s",
                        free_gb,
                        self.app_config.min_free_gb,
                        self.camera.name,
                    )
                    self._disk_low_last_log = now
                if self.disk_warning_cb is not None:
                    try:
                        self.disk_warning_cb(free_gb, float(self.app_config.min_free_gb))
                    except Exception:
                        self.logger.exception("Disk warning callback failed")
                if self.app_config.enable_disk_quota:
                    if writer is not None:
                        writer.release()
                        self._finalize_current(stamp)
                    return (
                        None,
                        hour_key,
                        float(config.get("record_fps", self.app_config.fps_record or 15)),
                    )
        next_hour_key = stamp.strftime("%Y%m%d%H")
        if writer is None or next_hour_key != hour_key:
            if writer is not None:
                writer.release()
                self._finalize_current(stamp)
            h, w = frame.shape[:2]
            base_fps = float(config.get("record_fps", self.app_config.fps_record or 15))
            writer = self._open_writer(w, h, base_fps, stamp)
            if not writer.isOpened():
                self.logger.error("Failed to open VideoWriter for %s", self.camera.name)
                return None, None, base_fps
            hour_key = next_hour_key
            self.logger.info("Recording to %s (%s)", self.camera.name, hour_key)
            return writer, hour_key, base_fps
        base_fps = float(config.get("record_fps", self.app_config.fps_record or 15))
        return writer, hour_key, base_fps

    def _handle_motion(
        self,
        frame,
        config: dict,
        base_fps: float,
        motion_prev_active: bool,
        stamp: datetime,
    ) -> bool:
        if not self._motion_enabled:
            if self._motion_writer is not None and motion_prev_active:
                self._motion_writer.stop_clip(datetime.now())
            self._motion_active = False
            self._motion_count = 0
            self._clip_hold_until = 0.0
            self._clip_start_ts = 0.0
            self._motion_capture_last_ts = 0.0
            return False

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
            boxes = [
                (int(x * inv), int(y * inv), int(w * inv), int(h * inv))
                for x, y, w, h in boxes
            ]
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
        return self._motion_active

    def _write_record_frame(
        self,
        frame,
        writer: cv2.VideoWriter,
        config: dict,
        last_write: float,
        now: float,
        base_fps: float,
    ) -> float:
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
            return last_write
        if self._motion_enabled and self._motion_active:
            while now - last_write >= interval:
                writer.write(frame)
                last_write += interval
            return last_write
        if now - last_write < interval:
            return last_write
        last_write = now
        writer.write(frame)
        return last_write

    def _update_fps(self, now: float) -> None:
        delta = now - self._last_fps_ts
        if delta <= 0:
            return
        inst_fps = 1.0 / delta
        self._fps = 0.9 * self._fps + 0.1 * inst_fps
        self._last_fps_ts = now

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
            frame = self._next_frame()
            if frame is None:
                continue

            config = get_motion_config()
            stamp = datetime.now()
            writer, current_hour_key, base_fps = self._ensure_writer(
                frame, stamp, writer, current_hour_key, config
            )
            if writer is None:
                time.sleep(0.2)
                continue
            motion_prev_active = self._handle_motion(
                frame, config, base_fps, motion_prev_active, stamp
            )

            now = time.time()
            last_write = self._write_record_frame(
                frame, writer, config, last_write, now, base_fps
            )
            self._update_fps(time.time())

        self._stop_capture()
        if writer is not None:
            writer.release()
            self._finalize_current(datetime.now())
        if self._motion_writer is not None:
            self._motion_writer.close()

    def _save_motion_capture(self, frame, stamp: datetime) -> None:
        capture_dir = motion_capture_dir_for(self.camera.name, stamp)
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
