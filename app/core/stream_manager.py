import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict

from app.core.camera_manager import CameraManager


@dataclass
class StreamDemand:
    reasons: Dict[str, int] = field(default_factory=dict)
    stop_at: float | None = None

    def total(self) -> int:
        return sum(self.reasons.values())


class StreamManager:
    def __init__(self, camera_manager: CameraManager, idle_timeout_s: float = 10.0) -> None:
        self._camera_manager = camera_manager
        self._idle_timeout_s = float(idle_timeout_s)
        self._lock = threading.Lock()
        self._demands: Dict[str, StreamDemand] = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._logger = logging.getLogger("StreamManager")
        self._thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2)

    def acquire(self, camera_name: str, reason: str) -> None:
        with self._lock:
            demand = self._demands.setdefault(camera_name, StreamDemand())
            demand.reasons[reason] = demand.reasons.get(reason, 0) + 1
            demand.stop_at = None
            total = demand.total()
        if total == 1:
            self._logger.info("Stream start %s (reason=%s)", camera_name, reason)
            self._camera_manager.start_stream(camera_name)

    def release(self, camera_name: str, reason: str) -> None:
        with self._lock:
            demand = self._demands.get(camera_name)
            if demand is None:
                return
            if reason in demand.reasons:
                demand.reasons[reason] = max(0, demand.reasons[reason] - 1)
                if demand.reasons[reason] == 0:
                    demand.reasons.pop(reason, None)
            if demand.total() == 0:
                demand.stop_at = time.time() + self._idle_timeout_s
                self._logger.info(
                    "Stream idle %s, stopping in %.1fs",
                    camera_name,
                    self._idle_timeout_s,
                )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            to_stop: list[str] = []
            with self._lock:
                for name, demand in self._demands.items():
                    if demand.total() == 0 and demand.stop_at is not None:
                        if now >= demand.stop_at:
                            to_stop.append(name)
                for name in to_stop:
                    self._demands.pop(name, None)
            for name in to_stop:
                self._logger.info("Stream stop %s (idle timeout)", name)
                self._camera_manager.stop_stream(name)
            self._stop_event.wait(0.5)
