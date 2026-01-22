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

    def placeholder(self, width: int, height: int, label: str) -> np.ndarray:
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
        return frame

    def compose(
        self,
        assignments: Dict[int, Optional[str]],
        frames: Dict[str, np.ndarray],
    ) -> np.ndarray:
        canvas = np.zeros((self.canvas_h, self.canvas_w, 3), dtype=np.uint8)
        for slot, (x, y, w, h) in SLOT_SPECS.items():
            name = assignments.get(slot)
            if name and name in frames:
                src = frames[name]
                resized = cv2.resize(src, (w, h))
                canvas[y : y + h, x : x + w] = resized
            else:
                canvas[y : y + h, x : x + w] = self.placeholder(w, h, f"Slot {slot+1}")
        return canvas

    def slot_at(self, x: int, y: int) -> Optional[int]:
        for slot, (sx, sy, w, h) in SLOT_SPECS.items():
            if sx <= x < sx + w and sy <= y < sy + h:
                return slot
        return None
