import logging
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
            return self._runtime[name]

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
            runtime = CameraRuntimeState(mode=config.mode)
            stop_event = threading.Event()
            self._cameras[config.name] = config
            self._runtime[config.name] = runtime
            if start_worker:
                worker = CameraWorker(
                    config=config,
                    runtime=runtime,
                    frame_store=self.frame_store,
                    stop_event=stop_event,
                )
                self._workers[config.name] = worker
                self._stop_events[config.name] = stop_event
                worker.start()
                self.logger.info("Started camera %s", config.name)
            else:
                self._stop_events[config.name] = stop_event

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

    def remove_camera(self, name: str, persist: bool = True) -> None:
        with self._lock:
            if name not in self._cameras:
                return
            stop_event = self._stop_events.get(name)
            if stop_event:
                stop_event.set()
            worker = self._workers.get(name)
            if worker:
                worker.join(timeout=5)
            self._stop_events.pop(name, None)
            self._workers.pop(name, None)
            del self._runtime[name]
            del self._cameras[name]
            self.logger.info("Stopped camera %s", name)

        if persist:
            self.persist()

    def persist(self) -> None:
        cameras = self.list_cameras()
        app_config, _ = self.config_store.load()
        self.config_store.save(app_config, cameras)

    def shutdown(self, join_timeout: float = 0.2) -> None:
        names = [c.name for c in self.list_cameras()]
        with self._lock:
            for name in names:
                if name in self._stop_events:
                    self._stop_events[name].set()
            for name in names:
                worker = self._workers.get(name)
                if worker:
                    worker.join(timeout=join_timeout)
            self._stop_events.clear()
            self._workers.clear()
            self._runtime.clear()
            self._cameras.clear()
