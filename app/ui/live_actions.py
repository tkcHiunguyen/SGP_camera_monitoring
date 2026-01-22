import tkinter as tk

from app.config.models import CameraConfig
from app.ui.widgets.live_popup import open_live_popup


def open_live(parent: tk.Misc, camera: CameraConfig) -> None:
    open_live_popup(parent, camera)
