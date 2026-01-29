import logging
import queue
import threading
import time
from pathlib import Path

import cv2

from app.storage.layout import tracking_output_path


class TrackingManager:
    def __init__(
        self, model_path: Path, conf_thres: float = 0.6, use_gpu: bool = True
    ) -> None:
        self.model_path = Path(model_path)
        self.conf_thres = conf_thres
        self.use_gpu = use_gpu
        self._queue: "queue.Queue[Path]" = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._model = None
        self.logger = logging.getLogger("TrackingManager")
        self._thread.start()
        self._last_track_error = 0.0

    def enqueue(self, video_path: Path) -> None:
        self._queue.put(Path(video_path))

    def shutdown(self) -> None:
        self._stop_event.set()
        self._queue.put(Path())
        self._thread.join(timeout=3)

    def _load_model(self):
        if self._model is not None:
            return self._model
        from ultralytics import YOLO

        self._model = YOLO(str(self.model_path))
        if self.use_gpu:
            try:
                self._model.to("cuda")
            except Exception as exc:
                self.logger.warning("GPU not available, fallback to CPU: %s", exc)
        return self._model

    def _run(self) -> None:
        while not self._stop_event.is_set():
            video_path = self._queue.get()
            if self._stop_event.is_set():
                break
            if not video_path or not video_path.exists():
                continue
            try:
                self._process_video(video_path)
            except Exception:
                self.logger.exception("Tracking failed for %s", video_path.name)

    def _process_video(self, video_path: Path) -> None:
        model = self._load_model()
        cap = self._open_capture(video_path)
        if cap is None:
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        width, height = 1280, 720
        out_path, writer = self._open_writer(video_path, fps, (width, height))
        if writer is None:
            cap.release()
            return
        try:
            self._process_stream(cap, writer, model, (width, height))
        finally:
            cap.release()
            writer.release()
        self.logger.info("Tracking saved: %s", out_path.name)

    def _open_capture(self, video_path: Path) -> cv2.VideoCapture | None:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            self.logger.warning("Cannot open video %s", video_path.name)
            return None
        return cap

    def _open_writer(
        self, video_path: Path, fps: float, size: tuple[int, int]
    ) -> tuple[Path, cv2.VideoWriter | None]:
        out_path = self._build_output_path(video_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, size)
        if not writer.isOpened():
            self.logger.warning("Cannot open writer for %s", out_path.name)
            return out_path, None
        return out_path, writer

    def _process_stream(
        self,
        cap: cv2.VideoCapture,
        writer: cv2.VideoWriter,
        model,
        size: tuple[int, int],
    ) -> None:
        prev_time = time.time()
        fps_val = 0.0
        names = getattr(model, "names", {})
        width, height = size
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            frame = cv2.resize(frame, (width, height))
            try:
                result = model.track(
                    frame,
                    conf=self.conf_thres,
                    verbose=True,
                    device=0 if self.use_gpu else "cpu",
                )[0]
                self._draw_detections(frame, result, names)
            except Exception:
                now = time.time()
                if now - self._last_track_error > 5.0:
                    self.logger.exception("Tracking inference failed")
                    self._last_track_error = now
            fps_val, prev_time = self._draw_fps(frame, fps_val, prev_time)
            writer.write(frame)

    def _draw_detections(self, frame, result, names: dict) -> None:
        boxes = result.boxes
        if boxes is None:
            return
        xyxy = boxes.xyxy.cpu().numpy()
        conf = boxes.conf.cpu().numpy()
        cls = boxes.cls.cpu().numpy().astype(int)
        for i, (x1, y1, x2, y2) in enumerate(xyxy):
            label = names.get(int(cls[i]), str(int(cls[i])))
            if label != "person" and int(cls[i]) != 0:
                continue
            x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"human {conf[i]:.2f}"
            (tw, th), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2
            )
            y_text = max(24, y1 - 6)
            cv2.rectangle(
                frame,
                (x1, y_text - th - baseline - 4),
                (x1 + tw + 6, y_text + 2),
                (0, 255, 0),
                -1,
            )
            cv2.putText(
                frame,
                label,
                (x1 + 3, y_text - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 0),
                2,
                cv2.LINE_AA,
            )

    def _draw_fps(self, frame, fps_val: float, prev_time: float) -> tuple[float, float]:
        now = time.time()
        inst_fps = 1.0 / max(1e-6, now - prev_time)
        prev_time = now
        fps_val = 0.9 * fps_val + 0.1 * inst_fps
        fps_label = f"FPS: {fps_val:.1f}"
        (tw, th), baseline = cv2.getTextSize(
            fps_label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2
        )
        cv2.rectangle(
            frame, (6, 6), (6 + tw + 10, 6 + th + baseline + 8), (0, 255, 0), -1
        )
        cv2.putText(
            frame,
            fps_label,
            (10, 6 + th + 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        return fps_val, prev_time

    def _build_output_path(self, video_path: Path) -> Path:
        return tracking_output_path(video_path)
