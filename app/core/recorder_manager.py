import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Dict, List

from app.config.models import AppConfig, CameraConfig
from app.core.recorder_worker import RecorderWorker


@dataclass
class RecorderJob:
    camera_name: str
    start_time: float
    status: str = "Recording"


class RecorderManager:
    def __init__(self, app_config: AppConfig, tracking_manager=None) -> None:
        self.app_config = app_config
        self.tracking_manager = tracking_manager
        self._lock = threading.Lock()
        self._workers: Dict[str, RecorderWorker] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._jobs: Dict[str, RecorderJob] = {}
        self._stop_queue: "queue.Queue[str | None]" = queue.Queue()
        self._stop_worker = threading.Thread(target=self._stop_loop, daemon=True)
        self._stop_worker.start()
        self.logger = logging.getLogger("RecorderManager")

    def start(self, camera: CameraConfig) -> None:
        with self._lock:
            if camera.name in self._workers:
                raise ValueError("Recorder already running for this camera")
            stop_event = threading.Event()
            worker = RecorderWorker(
                camera, self.app_config, stop_event, tracking_manager=self.tracking_manager
            )
            self._stop_events[camera.name] = stop_event
            self._workers[camera.name] = worker
            self._jobs[camera.name] = RecorderJob(
                camera_name=camera.name, start_time=time.time()
            )
            worker.start()
            self.logger.info("Recorder started for %s", camera.name)

    def stop(self, camera_name: str) -> None:
        self._stop_sync(camera_name)

    def queue_stop(self, camera_name: str) -> None:
        self._stop_queue.put(camera_name)

    def _stop_sync(self, camera_name: str) -> None:
        with self._lock:
            event = self._stop_events.pop(camera_name, None)
            worker = self._workers.pop(camera_name, None)
            job = self._jobs.get(camera_name)
        if event:
            event.set()
        if worker:
            worker.join(timeout=2)
        if job:
            job.status = "Stopped"
            with self._lock:
                self._jobs.pop(camera_name, None)

    def list_active(self) -> List[str]:
        with self._lock:
            return list(self._workers.keys())

    def list_jobs(self) -> List[RecorderJob]:
        with self._lock:
            return list(self._jobs.values())

    def shutdown(self) -> None:
        for name in self.list_active():
            self.stop(name)
        self._stop_queue.put(None)
        self._stop_worker.join(timeout=2)

    def _stop_loop(self) -> None:
        while True:
            name = self._stop_queue.get()
            if name is None:
                break
            try:
                self._stop_sync(name)
            finally:
                self._stop_queue.task_done()
