import logging
import queue
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import cv2

from app.core.motion_detector import apply_motion, ensure_motion, get_motion_config
from app.storage.layout import motion_capture_dir_for
from app.utils.paths import get_tracking_dir


class OfflineMotionManager:
    def __init__(self, workers: int = 1) -> None:
        self._queue: "queue.Queue[Path | None]" = queue.Queue()
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self.logger = logging.getLogger("OfflineMotion")
        self._workers = max(1, int(workers))
        for _ in range(self._workers):
            thread = threading.Thread(target=self._run, daemon=True)
            self._threads.append(thread)
            thread.start()

    def enqueue(self, video_path: Path) -> None:
        self._queue.put(Path(video_path))

    def shutdown(self) -> None:
        self._stop_event.set()
        for _ in range(self._workers):
            self._queue.put(None)
        for thread in self._threads:
            thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            item = self._queue.get()
            if item is None or self._stop_event.is_set():
                break
            if not item.exists():
                continue
            try:
                self._process_video(item)
            except Exception:
                self.logger.exception("Offline motion failed for %s", item.name)

    def _process_video(self, path: Path) -> None:
        camera_name = path.parent.name
        base_stamp = self._parse_stamp(path) or datetime.fromtimestamp(path.stat().st_mtime)
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            self.logger.warning("Cannot open video %s", path.name)
            return
        native_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        config = get_motion_config()
        active_fps = float(
            config.get("motion_offline_fps_active", config.get("motion_fps", 2.0) or 2.0)
        )
        idle_fps = float(config.get("motion_offline_fps_idle", 0.5) or 0.5)
        boost_seconds = float(
            config.get(
                "motion_offline_boost_seconds",
                max(2.0, float(config.get("stop_seconds", 5.0) or 5.0)),
            )
            or 5.0
        )
        if native_fps > 0:
            active_fps = min(active_fps, native_fps)
        active_fps = max(0.1, active_fps)
        idle_fps = max(0.1, min(idle_fps, active_fps))

        state = {"bg": None}
        motion_active = False
        motion_count = 0
        motion_last_seen = 0.0
        last_capture = 0.0
        clip_hold_until = 0.0
        clip_start_ts = 0.0
        writer = None
        clip_path: Optional[Path] = None
        clip_start_stamp: Optional[datetime] = None
        last_box = None

        start_frames = int(config.get("start_frames", 6) or 6)
        stop_seconds = float(config.get("stop_seconds", 5.0) or 5.0)
        clip_fps = float(config.get("clip_fps", 6.0) or 6.0)
        if native_fps > 0:
            clip_fps = native_fps
        clip_fps = max(0.1, clip_fps)
        capture_interval = float(config.get("motion_capture_seconds", 3.0) or 3.0)
        capture_interval = max(0.1, capture_interval)

        frame_index = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                frame_ts = frame_index / native_fps if native_fps > 0 else 0.0
                stamp = base_stamp + timedelta(seconds=frame_ts)
                boost = motion_active or (
                    motion_last_seen > 0 and (frame_ts - motion_last_seen) < boost_seconds
                )
                target_fps = active_fps if boost else idle_fps
                detect_stride = max(1, int(round(native_fps / target_fps))) if target_fps > 0 else 1
                do_detect = (frame_index % detect_stride) == 0

                merged_box = None
                if do_detect:
                    motion_frame, motion_scale = self._scale_motion_frame(frame, config)
                    ensure_motion(state, config)
                    boxes, _ = apply_motion(motion_frame, state, config)
                    merged_box = self._merge_boxes(boxes)
                    if merged_box and motion_scale < 1.0:
                        merged_box = self._scale_box_to_frame(
                            merged_box, motion_scale, frame
                        )
                    last_box = merged_box
                    if merged_box:
                        motion_count += 1
                        motion_last_seen = frame_ts
                        if not motion_active and motion_count >= start_frames:
                            motion_active = True
                    else:
                        motion_count = 0
                        if motion_active and (frame_ts - motion_last_seen) >= stop_seconds:
                            motion_active = False

                if motion_active:
                    self._draw_motion_labels(frame)
                    if last_box:
                        self._draw_motion_box(frame, last_box)
                    if frame_ts - last_capture >= capture_interval:
                        last_capture = frame_ts
                        self._save_capture(camera_name, frame, stamp)

                if writer is not None and motion_active:
                    writer.write(frame)

                if motion_active and writer is None:
                    clip_start_stamp = stamp
                    clip_start_ts = frame_ts
                    clip_path, writer = self._open_clip_writer(
                        camera_name, stamp, clip_fps, frame
                    )

                if not motion_active and writer is not None:
                    clip_hold = float(config.get("clip_hold_seconds", 6.0) or 6.0)
                    if clip_hold_until == 0.0:
                        clip_hold_until = frame_ts + clip_hold
                    if frame_ts >= clip_hold_until:
                        min_clip = float(config.get("clip_min_seconds", 2.0) or 2.0)
                        if clip_start_ts and (frame_ts - clip_start_ts) < min_clip:
                            self._close_clip(writer, clip_path, clip_start_stamp, stamp, keep=False)
                        else:
                            self._close_clip(writer, clip_path, clip_start_stamp, stamp, keep=True)
                        writer = None
                        clip_path = None
                        clip_start_stamp = None
                        clip_hold_until = 0.0
                        clip_start_ts = 0.0

                if not boost and not motion_active:
                    for _ in range(detect_stride - 1):
                        if not cap.grab():
                            break
                        frame_index += 1
                frame_index += 1
        finally:
            cap.release()
            if writer is not None:
                self._close_clip(writer, clip_path, clip_start_stamp, datetime.now(), keep=True)

    def _scale_motion_frame(self, frame, config: dict):
        scale = float(config.get("motion_scale", 0.1) or 0.1)
        scale = max(0.05, min(1.0, scale))
        if scale >= 1.0:
            return frame, 1.0
        h, w = frame.shape[:2]
        return (
            cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA),
            scale,
        )

    def _scale_box_to_frame(self, box, scale: float, frame) -> tuple[int, int, int, int]:
        x, y, w, h = box
        if scale <= 0:
            return box
        inv = 1.0 / scale
        x = int(round(x * inv))
        y = int(round(y * inv))
        w = int(round(w * inv))
        h = int(round(h * inv))
        fh, fw = frame.shape[:2]
        x = max(0, min(x, max(0, fw - 1)))
        y = max(0, min(y, max(0, fh - 1)))
        w = max(1, min(w, max(1, fw - x)))
        h = max(1, min(h, max(1, fh - y)))
        return x, y, w, h

    def _merge_boxes(self, boxes: list[tuple[int, int, int, int]] | None):
        if not boxes:
            return None
        x_min = min(b[0] for b in boxes)
        y_min = min(b[1] for b in boxes)
        x_max = max(b[0] + b[2] for b in boxes)
        y_max = max(b[1] + b[3] for b in boxes)
        return (x_min, y_min, max(1, x_max - x_min), max(1, y_max - y_min))

    def _parse_stamp(self, path: Path) -> Optional[datetime]:
        name = path.name
        match = re.search(r"(\d{2}-\d{2}-\d{4} \d{2}h\d{2}m\d{2}s)", name)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%d-%m-%Y %Hh%Mm%Ss")
        except ValueError:
            return None

    def _build_clip_dir(self, camera_name: str, stamp: datetime) -> Path:
        return (
            get_tracking_dir()
            / f"{stamp:%Y}"
            / f"{stamp:%m}"
            / f"{stamp:%d}"
            / camera_name
        )

    def _build_clip_name(
        self, camera_name: str, start: datetime, end: Optional[datetime] = None, suffix: str = ".mp4"
    ) -> str:
        if end is None:
            return f"{camera_name} motion {start:%d-%m-%Y %Hh%Mm%Ss}{suffix}"
        return (
            f"{camera_name} motion {start:%d-%m-%Y %Hh%Mm%Ss} - "
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

    def _open_clip_writer(
        self, camera_name: str, stamp: datetime, fps: float, frame
    ) -> tuple[Optional[Path], Optional[cv2.VideoWriter]]:
        out_dir = self._build_clip_dir(camera_name, stamp)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._unique_path(out_dir / self._build_clip_name(camera_name, stamp, suffix=".mp4"))
        h, w = frame.shape[:2]
        codec_options = ["mp4v"]
        for codec in codec_options:
            fourcc = cv2.VideoWriter_fourcc(*codec)
            try:
                writer = cv2.VideoWriter(str(out_path), cv2.CAP_FFMPEG, fourcc, fps, (w, h))
            except TypeError:
                writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
            if writer is not None and writer.isOpened():
                return out_path, writer
        return None, None

    def _close_clip(
        self,
        writer: cv2.VideoWriter,
        clip_path: Optional[Path],
        start: Optional[datetime],
        end: datetime,
        keep: bool = True,
    ) -> None:
        try:
            writer.release()
        except Exception:
            pass
        if clip_path is None or start is None:
            return
        if not keep:
            try:
                clip_path.unlink()
            except Exception:
                pass
            return
        target = clip_path.with_name(self._build_clip_name(clip_path.parent.name, start, end))
        target = self._unique_path(target)
        try:
            if clip_path.exists():
                clip_path.rename(target)
        except Exception:
            target = clip_path
        # mp4v writer already outputs mp4

    def _save_capture(self, camera_name: str, frame, stamp: datetime) -> None:
        capture_dir = motion_capture_dir_for(camera_name, stamp)
        capture_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{camera_name} motion {stamp:%d-%m-%Y %Hh%Mm%Ss}.jpg"
        cv2.imwrite(str(capture_dir / filename), frame)

    def _draw_motion_labels(self, frame) -> None:
        self._draw_label(frame, "Mode: motion on", 10, 30, bg=(0, 0, 0), fg=(255, 255, 255))
        self._draw_label(frame, "Motion detect", 10, 60, bg=(0, 160, 0), fg=(255, 255, 255))

    def _draw_motion_box(self, frame, box) -> None:
        if not box:
            return
        x, y, w, h = box
        if w <= 0 or h <= 0:
            return
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 255), 2)

    def _draw_label(self, frame, text, x, y, bg=(0, 0, 0), fg=(255, 255, 255)) -> None:
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
