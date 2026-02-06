import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Dict, List

from app.config.models import AppConfig, CameraConfig
from app.core.offline_motion_manager import OfflineMotionManager
from app.core.recorder_worker import RecorderWorker
from app.core.stream_manager import StreamManager
from app.core.frame_store import FrameStore
from app.storage.maintenance import prune_old_videos


@dataclass
class RecorderJob:
    camera_name: str
    start_time: float
    status: str = "Recording"
    fps: float = 0.0
    motion_enabled: bool = False


class RecorderManager:
    def __init__(
        self,
        app_config: AppConfig,
        tracking_manager=None,
        on_disk_warning=None,
        stream_manager: StreamManager | None = None,
        frame_store: FrameStore | None = None,
    ) -> None:
        self.app_config = app_config
        self.tracking_manager = tracking_manager
        self.logger = logging.getLogger("RecorderManager")
        self._disk_warning_cb = on_disk_warning
        self._disk_warning_last_ts = 0.0
        self._stream_manager = stream_manager
        self._frame_store = frame_store
        self._lock = threading.Lock()
        self._workers: Dict[str, RecorderWorker] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._jobs: Dict[str, RecorderJob] = {}
        self._stop_queue: "queue.Queue[str | None]" = queue.Queue()
        self._stop_worker = threading.Thread(target=self._stop_loop, daemon=True)
        self._stop_worker.start()
        self._maint_stop = threading.Event()
        self._maint_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self._maint_thread.start()
        self._offline_motion = (
            OfflineMotionManager(getattr(app_config, "motion_offline_workers", 1))
            if getattr(app_config, "motion_offline", False)
            else None
        )

    def is_motion_available(self) -> bool:
        return self._offline_motion is not None

    def start(self, camera: CameraConfig) -> None:
        with self._lock:
            if camera.name in self._workers:
                raise ValueError("Recorder already running for this camera")
            stop_event = threading.Event()
            worker = self._create_worker(camera, stop_event)
            self._stop_events[camera.name] = stop_event
            self._workers[camera.name] = worker
            self._jobs[camera.name] = self._create_job(camera.name)
        if (
            self._stream_manager is not None
            and getattr(self.app_config, "record_backend", "opencv") != "ffmpeg_copy"
        ):
            self._stream_manager.acquire(camera.name, "record")
        self._start_worker(worker, camera.name)

    def stop(self, camera_name: str) -> None:
        self._stop_sync(camera_name)

    def queue_stop(self, camera_name: str) -> None:
        self._stop_queue.put(camera_name)

    def _stop_sync(self, camera_name: str) -> None:
        with self._lock:
            event = self._stop_events.pop(camera_name, None)
            worker = self._workers.pop(camera_name, None)
            job = self._jobs.pop(camera_name, None)
        if event:
            event.set()
        if worker:
            worker.join(timeout=2)
        if job:
            job.status = "Stopped"
        if (
            self._stream_manager is not None
            and getattr(self.app_config, "record_backend", "opencv") != "ffmpeg_copy"
        ):
            self._stream_manager.release(camera_name, "record")

    def list_active(self) -> List[str]:
        with self._lock:
            return list(self._workers.keys())

    def list_jobs(self) -> List[RecorderJob]:
        with self._lock:
            jobs = list(self._jobs.values())
            workers = dict(self._workers)
        for job in jobs:
            worker = workers.get(job.camera_name)
            if worker is not None:
                job.fps = worker.get_fps()
                job.motion_enabled = worker.get_motion_enabled()
        return jobs

    def set_job_motion_enabled(self, camera_name: str, enabled: bool) -> None:
        with self._lock:
            job = self._jobs.get(camera_name)
            worker = self._workers.get(camera_name)
        if job is not None:
            job.motion_enabled = bool(enabled)
        if worker is not None:
            worker.set_motion_enabled(bool(enabled))

    def shutdown(self) -> None:
        for name in self.list_active():
            self.stop(name)
        self._stop_queue.put(None)
        self._stop_worker.join(timeout=2)
        self._maint_stop.set()
        self._maint_thread.join(timeout=2)
        if self._offline_motion is not None:
            self._offline_motion.shutdown()

    def _stop_loop(self) -> None:
        while True:
            name = self._stop_queue.get()
            if name is None:
                break
            try:
                self._stop_sync(name)
            finally:
                self._stop_queue.task_done()

    def _maintenance_loop(self) -> None:
        while not self._maint_stop.is_set():
            try:
                if self.app_config.enable_retention:
                    deleted = prune_old_videos(self.app_config.days_keep)
                    if deleted:
                        self.logger.info("Retention deleted %s files", deleted)
            except Exception:
                self.logger.exception("Retention cleanup failed")
            self._maint_stop.wait(3600)

    def _create_worker(
        self, camera: CameraConfig, stop_event: threading.Event
    ) -> RecorderWorker:
        return RecorderWorker(
            camera,
            self.app_config,
            stop_event,
            tracking_manager=self.tracking_manager,
            disk_warning_cb=self._handle_disk_warning,
            offline_motion_manager=self._offline_motion,
            frame_store=self._frame_store,
        )

    def _create_job(self, camera_name: str) -> RecorderJob:
        return RecorderJob(
            camera_name=camera_name,
            start_time=time.time(),
            motion_enabled=False,
        )

    def _start_worker(self, worker: RecorderWorker, camera_name: str) -> None:
        worker.start()
        self.logger.info("Recorder started for %s", camera_name)

    def _handle_disk_warning(self, free_gb: float, min_gb: float) -> None:
        if self._disk_warning_cb is None:
            return
        now = time.time()
        if now - self._disk_warning_last_ts < 30.0:
            return
        self._disk_warning_last_ts = now
        self._disk_warning_cb(free_gb, min_gb)
