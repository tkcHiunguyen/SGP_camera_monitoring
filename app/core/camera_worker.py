import logging
import threading
import time
from typing import Callable, Optional

import cv2

from app.config.models import CameraConfig, CameraRuntimeState
from app.core.frame_store import FrameStore
from app.utils.rtsp import build_rtsp_url


class CameraWorker(threading.Thread):
    def __init__(
        self,
        config: CameraConfig,
        runtime: CameraRuntimeState,
        frame_store: FrameStore,
        stop_event: threading.Event,
        min_backoff_s: float = 0.5,
        max_backoff_s: float = 30.0,
        status_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.config = config
        self.runtime = runtime
        self.frame_store = frame_store
        self.stop_event = stop_event
        self._min_backoff_s = float(min_backoff_s)
        self._max_backoff_s = float(max_backoff_s)
        self._reconnect_attempts = 0
        self.status_callback = status_callback
        self.logger = logging.getLogger(f"CameraWorker[{config.name}]")

    def set_status(self, status: str, error: str = "") -> None:
        self.runtime.status = status
        self.runtime.last_error = error
        if self.status_callback:
            self.status_callback(self.config.name, status)

    def _open_capture(self) -> cv2.VideoCapture:
        if self.config.source == "device":
            self.logger.info("Opening device index %s", self.config.device_index)
            return cv2.VideoCapture(self.config.device_index)
        url = build_rtsp_url(self.config)
        self.logger.info("Connecting to %s", url)
        return cv2.VideoCapture(url, cv2.CAP_FFMPEG)

    def _read_frame(self, cap: cv2.VideoCapture) -> Optional[cv2.Mat]:
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        return frame

    def _sleep_backoff(self, backoff: float) -> float:
        time.sleep(backoff)
        return min(backoff * 2, self._max_backoff_s)

    def run(self) -> None:
        backoff = self._min_backoff_s
        while not self.stop_event.is_set():
            cap = self._open_capture()
            if not cap.isOpened():
                self.set_status("Offline", "Open failed")
                self._reconnect_attempts += 1
                self.logger.warning(
                    "Open failed; retry #%s in %.1fs", self._reconnect_attempts, backoff
                )
                backoff = self._sleep_backoff(backoff)
                continue

            self.set_status("Online")
            backoff = self._min_backoff_s
            self._reconnect_attempts = 0

            while not self.stop_event.is_set():
                frame = self._read_frame(cap)
                if frame is None:
                    self.set_status("Offline", "Read failed")
                    self._reconnect_attempts += 1
                    self.logger.warning(
                        "Read failed; reconnect #%s", self._reconnect_attempts
                    )
                    break

                self.runtime.last_frame_ts = time.time()
                self.frame_store.set_frame(
                    self.config.name, frame, self.runtime.last_frame_ts
                )

            cap.release()
            if not self.stop_event.is_set():
                backoff = self._sleep_backoff(backoff)
