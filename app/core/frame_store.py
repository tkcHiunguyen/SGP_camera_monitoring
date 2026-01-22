import threading
from typing import Dict, Optional

import numpy as np


class FrameStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frames: Dict[str, np.ndarray] = {}

    def set_frame(self, camera_name: str, frame: np.ndarray) -> None:
        with self._lock:
            self._frames[camera_name] = frame

    def get_frame(self, camera_name: str) -> Optional[np.ndarray]:
        with self._lock:
            frame = self._frames.get(camera_name)
            return frame.copy() if frame is not None else None

    def list_cameras(self) -> list[str]:
        with self._lock:
            return list(self._frames.keys())
