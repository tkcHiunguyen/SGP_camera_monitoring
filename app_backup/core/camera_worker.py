import logging
import threading
import time
from typing import Callable, Optional
from urllib.parse import quote

import cv2

from app.config.models import CameraConfig, CameraRuntimeState
from app.core.frame_store import FrameStore


class CameraWorker(threading.Thread):
    def __init__(
        self,
        config: CameraConfig,
        runtime: CameraRuntimeState,
        frame_store: FrameStore,
        stop_event: threading.Event,
        status_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.config = config
        self.runtime = runtime
        self.frame_store = frame_store
        self.stop_event = stop_event
        self.status_callback = status_callback
        self.logger = logging.getLogger(f"CameraWorker[{config.name}]")

    def build_rtsp_url(self) -> str:
        if self.config.rtsp_url:
            return self.config.rtsp_url
        user = quote(self.config.user, safe="")
        password = quote(self.config.password, safe="")
        auth = f"{user}:{password}@" if user or password else ""
        return f"rtsp://{auth}{self.config.ip}:{self.config.port}{self.config.stream_path}"

    def set_status(self, status: str, error: str = "") -> None:
        self.runtime.status = status
        self.runtime.last_error = error
        if self.status_callback:
            self.status_callback(self.config.name, status)

    def run(self) -> None:
        backoff = 1.0
        while not self.stop_event.is_set():
            if self.config.source == "device":
                self.logger.info("Opening device index %s", self.config.device_index)
                cap = cv2.VideoCapture(self.config.device_index)
            else:
                url = self.build_rtsp_url()
                self.logger.info("Connecting to %s", url)
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                self.set_status("Offline", "Open failed")
                self.logger.warning("Open failed; retry in %.1fs", backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            self.set_status("Online")
            backoff = 1.0

            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    self.set_status("Offline", "Read failed")
                    self.logger.warning("Read failed; reconnect")
                    break

                self.runtime.last_frame_ts = time.time()
                self.frame_store.set_frame(self.config.name, frame)

            cap.release()
            if not self.stop_event.is_set():
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
