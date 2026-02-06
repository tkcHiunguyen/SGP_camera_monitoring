import threading
from typing import Dict, Optional, Tuple

import numpy as np


class FrameStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frames: Dict[str, np.ndarray] = {}
        self._timestamps: Dict[str, float] = {}

    def set_frame(self, camera_name: str, frame: np.ndarray, timestamp: float) -> None:
        with self._lock:
            self._frames[camera_name] = frame
            self._timestamps[camera_name] = float(timestamp)

    def get_frame(self, camera_name: str) -> Optional[np.ndarray]:
        with self._lock:
            frame = self._frames.get(camera_name)
            return frame.copy() if frame is not None else None

    def get_frame_with_ts(
        self, camera_name: str
    ) -> Optional[Tuple[np.ndarray, float]]:
        with self._lock:
            frame = self._frames.get(camera_name)
            if frame is None:
                return None
            return frame.copy(), float(self._timestamps.get(camera_name, 0.0))

    def get_latest_frames(self) -> Dict[str, np.ndarray]:
        with self._lock:
            return {name: frame.copy() for name, frame in self._frames.items()}

    def get_latest_snapshot(self) -> Dict[str, Tuple[np.ndarray, float]]:
        with self._lock:
            return {
                name: (frame.copy(), self._timestamps.get(name, 0.0))
                for name, frame in self._frames.items()
            }

    def list_cameras(self) -> list[str]:
        with self._lock:
            return list(self._frames.keys())

    def remove_frame(self, camera_name: str) -> None:
        with self._lock:
            self._frames.pop(camera_name, None)
            self._timestamps.pop(camera_name, None)
