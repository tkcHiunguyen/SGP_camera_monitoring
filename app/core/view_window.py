import threading
from typing import Callable, Dict, Optional

import cv2

from app.core.view_composer import ViewComposer
from app.core.frame_store import FrameStore


class ViewWindow:
    def __init__(
        self,
        composer: ViewComposer,
        slot_menu_callback: Callable[[int], None],
        frame_provider: Optional[Callable[[], Dict[str, object]]] = None,
        frame_store: Optional[FrameStore] = None,
    ) -> None:
        self.composer = composer
        if frame_provider is not None:
            self.frame_provider = frame_provider
        elif frame_store is not None:
            self.frame_provider = frame_store.get_latest_frames
        else:
            raise ValueError("frame_provider or frame_store is required")
        self.slot_menu_callback = slot_menu_callback
        self.assignments: Dict[int, Optional[str]] = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._fullscreen = True

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=3)
        cv2.destroyAllWindows()

    def assign_slot(self, slot: int, camera_name: Optional[str]) -> None:
        self.assignments[slot] = camera_name

    def _toggle_fullscreen(self) -> None:
        if self._fullscreen:
            cv2.setWindowProperty("view", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            self._fullscreen = False
        else:
            cv2.setWindowProperty(
                "view", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
            )
            self._fullscreen = True

    def _on_mouse(self, event: int, x: int, y: int, flags: int, param: object) -> None:
        if event == cv2.EVENT_RBUTTONUP:
            slot = self.composer.slot_at(x, y)
            if slot is not None:
                self.slot_menu_callback(slot)

    def _init_window(self) -> None:
        cv2.namedWindow("view", cv2.WINDOW_NORMAL)
        cv2.setWindowProperty("view", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.setMouseCallback("view", self._on_mouse)

    def _run(self) -> None:
        self._init_window()

        while not self._stop_event.is_set():
            frames = self.frame_provider()
            canvas = self.composer.compose(self.assignments, frames)
            cv2.imshow("view", canvas)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                self._toggle_fullscreen()
