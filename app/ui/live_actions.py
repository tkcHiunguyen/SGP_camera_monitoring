import tkinter as tk

from app.config.models import CameraConfig
from app.core.stream_manager import StreamManager
from app.core.frame_store import FrameStore
from app.ui.widgets.live_popup import open_live_popup


def open_live(
    parent: tk.Misc,
    camera: CameraConfig,
    stream_manager: StreamManager,
    frame_store: FrameStore,
) -> None:
    open_live_popup(parent, camera, stream_manager, frame_store)
