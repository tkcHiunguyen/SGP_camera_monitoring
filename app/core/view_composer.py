from typing import Dict, Optional, Tuple

import cv2
import numpy as np


SLOT_SPECS: Dict[int, Tuple[int, int, int, int]] = {
    0: (0, 0, 1280, 720),
    1: (0, 720, 640, 360),
    2: (640, 720, 640, 360),
    3: (1280, 0, 640, 360),
    4: (1280, 360, 640, 360),
    5: (1280, 720, 640, 360),
}


class ViewComposer:
    def __init__(self, canvas_size: Tuple[int, int] = (1920, 1080)) -> None:
        self.canvas_w, self.canvas_h = canvas_size
        self._placeholder_cache: Dict[Tuple[int, int, str], np.ndarray] = {}

    def placeholder(self, width: int, height: int, label: str) -> np.ndarray:
        key = (width, height, label)
        cached = self._placeholder_cache.get(key)
        if cached is not None:
            return cached.copy()
        frame = np.full((height, width, 3), 30, dtype=np.uint8)
        cv2.putText(
            frame,
            label,
            (10, max(30, height // 2)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (200, 200, 200),
            2,
            cv2.LINE_AA,
        )
        self._placeholder_cache[key] = frame
        return frame.copy()

    def compose(
        self,
        assignments: Dict[int, Optional[str]],
        frames: Dict[str, np.ndarray],
    ) -> np.ndarray:
        canvas = np.zeros((self.canvas_h, self.canvas_w, 3), dtype=np.uint8)
        for slot, (x, y, w, h) in SLOT_SPECS.items():
            name = assignments.get(slot)
            if name and name in frames:
                canvas[y : y + h, x : x + w] = self._resize_slot(frames[name], w, h)
            else:
                canvas[y : y + h, x : x + w] = self.placeholder(w, h, f"Slot {slot+1}")
        return canvas

    @staticmethod
    def _resize_slot(frame: np.ndarray, width: int, height: int) -> np.ndarray:
        return cv2.resize(frame, (width, height))

    def slot_at(self, x: int, y: int) -> Optional[int]:
        for slot, (sx, sy, w, h) in SLOT_SPECS.items():
            if sx <= x < sx + w and sy <= y < sy + h:
                return slot
        return None
