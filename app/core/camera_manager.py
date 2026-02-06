import logging
import time
import threading
from typing import Dict, List, Tuple

from app.config.models import CameraConfig, CameraRuntimeState
from app.config.store import ConfigStore
from app.core.camera_worker import CameraWorker
from app.core.frame_store import FrameStore


class CameraManager:
    def __init__(self, config_store: ConfigStore, frame_store: FrameStore) -> None:
        self.config_store = config_store
        self.frame_store = frame_store
        self._app_config, _ = self.config_store.load()
        self._lock = threading.Lock()
        self._cameras: Dict[str, CameraConfig] = {}
        self._runtime: Dict[str, CameraRuntimeState] = {}
        self._workers: Dict[str, CameraWorker] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self.logger = logging.getLogger("CameraManager")

    def load_from_config(self, cameras: List[CameraConfig], start_workers: bool = False) -> None:
        for cam in cameras:
            self.add_camera(cam, persist=False, start_worker=start_workers)

    def list_cameras(self) -> List[CameraConfig]:
        with self._lock:
            return list(self._cameras.values())

    def get_runtime(self, name: str) -> CameraRuntimeState:
        with self._lock:
            runtime = self._runtime[name]
            if self._app_config.cam_stale_s > 0 and runtime.last_frame_ts:
                age = time.time() - runtime.last_frame_ts
                if age > self._app_config.cam_stale_s and runtime.status == "Online":
                    runtime.status = "Offline"
                    runtime.last_error = "Stale"
            return runtime

    def get_camera(self, name: str) -> CameraConfig:
        with self._lock:
            return self._cameras[name]

    def get_snapshot(self) -> List[Tuple[CameraConfig, CameraRuntimeState]]:
        with self._lock:
            return [
                (self._cameras[name], self._runtime[name])
                for name in self._cameras.keys()
            ]

    def add_camera(
        self, config: CameraConfig, persist: bool = True, start_worker: bool = True
    ) -> None:
        with self._lock:
            if config.name in self._cameras:
                raise ValueError("Camera name already exists")
            runtime = CameraRuntimeState(mode=config.mode, enabled=config.enabled)
            stop_event = threading.Event()
            self._cameras[config.name] = config
            self._runtime[config.name] = runtime
            self._stop_events[config.name] = stop_event
        if start_worker:
            worker = self._create_worker(config, runtime, stop_event)
            self._register_worker(config.name, worker)
            self._start_worker(config.name, worker)

        if persist:
            self.persist()

    def update_camera(
        self, name: str, new_config: CameraConfig, start_worker: bool = False
    ) -> None:
        with self._lock:
            if name not in self._cameras:
                raise ValueError("Camera not found")
        self.remove_camera(name, persist=False)
        self.add_camera(new_config, persist=False, start_worker=start_worker)
        self.persist()

    def set_camera_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            if name not in self._cameras:
                return
            self._cameras[name].enabled = bool(enabled)
            if name in self._runtime:
                self._runtime[name].enabled = bool(enabled)
                if not enabled:
                    self._runtime[name].status = "disabled"
        self.persist()

    def remove_camera(self, name: str, persist: bool = True) -> None:
        stop_event, worker = self._pop_worker(name)
        if stop_event is None:
            return
        stop_event.set()
        if worker:
            worker.join(timeout=5)
        self.logger.info("Stopped camera %s", name)

        if persist:
            self.persist()

    def persist(self) -> None:
        cameras = self.list_cameras()
        app_config, _ = self.config_store.load()
        self.config_store.save(app_config, cameras)

    def shutdown(self, join_timeout: float = 0.2) -> None:
        with self._lock:
            stop_events = list(self._stop_events.values())
            workers = list(self._workers.values())
            self._stop_events.clear()
            self._workers.clear()
            self._runtime.clear()
            self._cameras.clear()
        for event in stop_events:
            event.set()
        for worker in workers:
            worker.join(timeout=join_timeout)

    def start_stream(self, name: str) -> None:
        with self._lock:
            if name not in self._cameras:
                raise ValueError("Camera not found")
            worker = self._workers.get(name)
            if worker is not None and worker.is_alive():
                return
            config = self._cameras[name]
            if not config.enabled:
                return
            runtime = self._runtime[name]
            stop_event = threading.Event()
            self._stop_events[name] = stop_event
            worker = self._create_worker(config, runtime, stop_event)
            self._workers[name] = worker
        self._start_worker(name, worker)

    def stop_stream(self, name: str, join_timeout: float = 2.0) -> None:
        with self._lock:
            stop_event = self._stop_events.pop(name, None)
            worker = self._workers.pop(name, None)
            runtime = self._runtime.get(name)
        if stop_event is not None:
            stop_event.set()
        if worker is not None:
            worker.join(timeout=join_timeout)
        if runtime is not None:
            runtime.status = "Offline"
        self.frame_store.remove_frame(name)

    def _create_worker(
        self,
        config: CameraConfig,
        runtime: CameraRuntimeState,
        stop_event: threading.Event,
    ) -> CameraWorker:
        return CameraWorker(
            config=config,
            runtime=runtime,
            frame_store=self.frame_store,
            stop_event=stop_event,
            min_backoff_s=self._app_config.cam_reconnect_min_s,
            max_backoff_s=self._app_config.cam_reconnect_max_s,
        )

    def _register_worker(self, name: str, worker: CameraWorker) -> None:
        with self._lock:
            self._workers[name] = worker

    def _start_worker(self, name: str, worker: CameraWorker) -> None:
        worker.start()
        self.logger.info("Started camera %s", name)

    def _pop_worker(
        self, name: str
    ) -> tuple[threading.Event | None, CameraWorker | None]:
        with self._lock:
            if name not in self._cameras:
                return None, None
            stop_event = self._stop_events.pop(name, None)
            worker = self._workers.pop(name, None)
            self._runtime.pop(name, None)
            self._cameras.pop(name, None)
        return stop_event, worker
