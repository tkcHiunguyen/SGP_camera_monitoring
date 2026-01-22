import logging
import queue
import threading
import time
from pathlib import Path

import cv2

from app.utils.paths import get_tracking_dir, get_videos_dir


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
            except Exception as exc:
                self.logger.warning("Tracking failed for %s: %s", video_path.name, exc)

    def _process_video(self, video_path: Path) -> None:
        model = self._load_model()
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            self.logger.warning("Cannot open video %s", video_path.name)
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        width = 1280
        height = 720

        out_path = self._build_output_path(video_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
        if not writer.isOpened():
            self.logger.warning("Cannot open writer for %s", out_path.name)
            cap.release()
            return

        prev_time = time.time()
        fps_val = 0.0
        names = getattr(model, "names", {})

        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            frame = cv2.resize(frame, (width, height))
            result = model.track(
                frame,
                conf=self.conf_thres,
                verbose=True,
                device=0 if self.use_gpu else "cpu",
            )[0]
            boxes = result.boxes
            if boxes is not None:
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
            writer.write(frame)

        cap.release()
        writer.release()
        self.logger.info("Tracking saved: %s", out_path.name)

    def _build_output_path(self, video_path: Path) -> Path:
        try:
            rel = video_path.relative_to(get_videos_dir())
        except ValueError:
            rel = video_path.name
            rel = Path(rel)
        return get_tracking_dir() / rel
