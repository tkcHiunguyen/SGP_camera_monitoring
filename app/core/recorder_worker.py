import logging
import os
import subprocess
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import cv2

from app.config.models import AppConfig, CameraConfig
from app.core.frame_store import FrameStore
from app.storage.layout import videos_dir_for
from app.storage.maintenance import get_free_gb, has_min_free_gb
from app.utils.ffmpeg import remux_ts_to_mp4, find_ffmpeg
from app.utils.paths import get_videos_dir
from app.utils.rtsp import build_rtsp_url
try:
    from app.utils.perf_probe import PerfProbe
except Exception:
    PerfProbe = None


class RecorderWorker(threading.Thread):
    def __init__(
        self,
        camera: CameraConfig,
        app_config: AppConfig,
        stop_event: threading.Event,
        tracking_manager=None,
        disk_warning_cb: Optional[Callable[[float, float], None]] = None,
        offline_motion_manager=None,
        frame_store: FrameStore | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.camera = camera
        self.app_config = app_config
        self.stop_event = stop_event
        self.tracking_manager = tracking_manager
        self.disk_warning_cb = disk_warning_cb
        self._offline_motion_manager = offline_motion_manager
        self.logger = logging.getLogger(f"Recorder[{camera.name}]")
        self._fps = 0.0
        self._last_fps_ts = time.time()
        self._motion_enabled = False
        self._disk_low_last_log = 0.0
        self._frame_queue: "queue.Queue[cv2.Mat | None]" = queue.Queue(maxsize=8)
        self._capture_thread: Optional[threading.Thread] = None
        self._capture_stop = threading.Event()
        self._record_backend = getattr(app_config, "record_backend", "opencv")
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._current_path: Optional[Path] = None
        self._current_start: Optional[datetime] = None
        self._frame_store = frame_store
        self._last_shared_ts = 0.0
        self._perf = None
        if PerfProbe is not None and os.environ.get("PERF_PROBE"):
            self._perf = PerfProbe(f"recorder_{camera.name}")

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
        if self._frame_store is not None:
            return
        self._capture_stop.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True
        )
        self._capture_thread.start()

    def _stop_capture(self) -> None:
        if self._frame_store is not None:
            return
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
            if self._perf is not None:
                self._perf.record_capture(grabbed=1, queue_size=self._frame_queue.qsize())
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                time.sleep(0.02)
                cap.release()
                cap = None
                continue
            try:
                self._frame_queue.put_nowait(frame)
                if self._perf is not None:
                    self._perf.record_capture(decoded=1, queued=1)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._frame_queue.put_nowait(frame)
                    if self._perf is not None:
                        self._perf.record_capture(decoded=1, queued=1, dropped=1)
                except queue.Full:
                    if self._perf is not None:
                        self._perf.record_capture(decoded=1, dropped=1)
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

    def _start_ffmpeg_recording(self, out_path: Path) -> Optional[subprocess.Popen]:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            self.logger.warning("ffmpeg not found; cannot use ffmpeg_copy backend")
            return None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        target_kbps = int(getattr(self.app_config, "record_bitrate_kbps", 4000) or 4000)
        maxrate_kbps = max(1, int(target_kbps * 1.1))
        bufsize_kbps = max(1, int(target_kbps * 2))
        fps = max(1, int(getattr(self.app_config, "fps_record", 15) or 15))
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-rtsp_transport",
            "tcp",
            "-i",
            self._build_rtsp_url(),
            "-map",
            "0",
            "-c:v",
            "libx265",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-b:v",
            f"{target_kbps}k",
            "-maxrate",
            f"{maxrate_kbps}k",
            "-bufsize",
            f"{bufsize_kbps}k",
            "-fps_mode",
            "cfr",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "mpegts",
            str(out_path),
        ]
        try:
            return subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as exc:
            self.logger.warning("Failed to start ffmpeg: %s", exc)
            return None

    def _stop_ffmpeg_recording(self, stamp: datetime) -> None:
        proc = self._ffmpeg_proc
        if proc is None:
            return
        self._ffmpeg_proc = None
        try:
            if proc.poll() is None and proc.stdin is not None:
                try:
                    proc.stdin.write(b"q\n")
                    proc.stdin.flush()
                except Exception:
                    pass
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._finalize_current(stamp, transcode=False)

    def _ensure_ffmpeg_process(
        self,
        stamp: datetime,
        current_hour_key: Optional[str],
    ) -> Optional[str]:
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
                    self._stop_ffmpeg_recording(stamp)
                    return current_hour_key
        next_hour_key = stamp.strftime("%Y%m%d%H")
        if (
            self._ffmpeg_proc is None
            or self._ffmpeg_proc.poll() is not None
            or current_hour_key != next_hour_key
        ):
            if self._ffmpeg_proc is not None:
                self._stop_ffmpeg_recording(stamp)
            out_path = self._build_output_path(stamp, suffix=".ts")
            self._current_path = out_path
            self._current_start = stamp
            self._ffmpeg_proc = self._start_ffmpeg_recording(out_path)
            if self._ffmpeg_proc is None:
                return None
            self.logger.info("FFmpeg recording to %s", out_path.name)
            current_hour_key = next_hour_key
        return current_hour_key

    def _finalize_current(self, end: datetime, transcode: bool = True) -> Optional[Path]:
        if not self._current_path or not self._current_start:
            return None
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
                mp4_path = self._try_remux_to_mp4(target, transcode=transcode)
                if mp4_path is not None:
                    target = mp4_path
            self._enqueue_offline_motion(target)
            return target
        except Exception as exc:
            self.logger.warning("Failed to finalize filename: %s", exc)
            return None
        finally:
            self._current_path = None
            self._current_start = None

    def _try_remux_to_mp4(self, ts_path: Path, transcode: bool = True) -> Optional[Path]:
        mp4_path = remux_ts_to_mp4(ts_path, delete_source=True, transcode=transcode)
        if mp4_path is not None and self.tracking_manager is not None:
            self.tracking_manager.enqueue(mp4_path)
        return mp4_path

    def _enqueue_offline_motion(self, video_path: Path | None) -> None:
        if (
            self._offline_motion_manager is None
            or video_path is None
            or not bool(getattr(self.app_config, "motion_offline", True))
            or not self._motion_enabled
        ):
            return
        try:
            self._offline_motion_manager.enqueue(video_path)
        except Exception:
            self.logger.exception("Failed to enqueue offline motion for %s", video_path)

    def _next_frame(self) -> Optional[cv2.Mat]:
        if self._frame_store is not None:
            return self._next_shared_frame()
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

    def _next_shared_frame(self) -> Optional[cv2.Mat]:
        if self._frame_store is None:
            return None
        deadline = time.time() + 0.2
        while not self.stop_event.is_set():
            data = self._frame_store.get_frame_with_ts(self.camera.name)
            if data is None:
                if time.time() > deadline:
                    return None
                time.sleep(0.02)
                continue
            frame, ts = data
            if ts <= self._last_shared_ts:
                if time.time() > deadline:
                    return None
                time.sleep(0.02)
                continue
            self._last_shared_ts = ts
            return frame
        return None

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

    def _write_record_frame(
        self,
        frame,
        writer: cv2.VideoWriter,
        config: dict,
        last_write: float,
        now: float,
        base_fps: float,
    ) -> float:
        base_fps = max(0.1, base_fps)
        interval = 1.0 / base_fps

        if last_write == 0.0:
            last_write = now
            writer.write(frame)
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
        if self._record_backend == "ffmpeg_copy":
            self._run_ffmpeg_copy()
            return
        self._run_opencv()

    def _run_opencv(self) -> None:
        last_write = 0.0
        writer: Optional[cv2.VideoWriter] = None
        current_hour_key: Optional[str] = None
        self._current_path = None
        self._current_start = None
        self._start_capture()

        while not self.stop_event.is_set():
            frame = self._next_frame()
            if frame is None:
                continue

            config: dict = {}
            stamp = datetime.now()
            writer, current_hour_key, base_fps = self._ensure_writer(
                frame, stamp, writer, current_hour_key, config
            )
            if writer is None:
                time.sleep(0.2)
                continue

            now = time.time()
            last_write = self._write_record_frame(
                frame, writer, config, last_write, now, base_fps
            )
            self._update_fps(time.time())
            if self._perf is not None:
                self._perf.record_write(
                    written=1,
                    motion=0,
                    fps=self._fps,
                    queue_size=self._frame_queue.qsize(),
                )

        self._stop_capture()
        if writer is not None:
            writer.release()
            self._finalize_current(datetime.now())

    def _run_ffmpeg_copy(self) -> None:
        if not find_ffmpeg():
            self.logger.warning("ffmpeg not available; falling back to OpenCV recorder")
            self._record_backend = "opencv"
            self._run_opencv()
            return

        current_hour_key: Optional[str] = None
        self._current_path = None
        self._current_start = None
        while not self.stop_event.is_set():
            stamp = datetime.now()
            current_hour_key = self._ensure_ffmpeg_process(stamp, current_hour_key)
            time.sleep(0.5)
        if self._ffmpeg_proc is not None:
            self._stop_ffmpeg_recording(datetime.now())
