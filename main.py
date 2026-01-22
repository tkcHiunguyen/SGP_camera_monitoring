import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import ctypes

from app.config.store import ConfigStore
from app.core.camera_manager import CameraManager
from app.core.frame_store import FrameStore
from app.core.recorder_manager import RecorderManager
from app.core.tracking_manager import TrackingManager
from app.ui.app_ui import AppUI
from app.ui.stop_jobs_dialog import StopJobsDialog
from app.utils.logging_setup import setup_logging

APP_NAME = "Camera Recorder"

def ensure_single_instance() -> bool:
    mutex_name = f"Global\\{APP_NAME}".replace(" ", "_")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if not mutex:
        return False
    last_error = ctypes.get_last_error()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        return False
    return True


def main() -> int:
    if not ensure_single_instance():
        return 1

    setup_logging()
    config_store = ConfigStore()
    app_config, cameras = config_store.load()

    root = tk.Tk()
    frame_store = FrameStore()
    camera_manager = CameraManager(config_store, frame_store)
    camera_manager.load_from_config(cameras, start_workers=False)
    tracking_manager = None
    if app_config.tracking.enabled:
        tracking_manager = TrackingManager(
            Path(app_config.tracking.model_path),
            conf_thres=app_config.tracking.conf_thres,
            use_gpu=app_config.tracking.use_gpu,
        )
    recorder_manager = RecorderManager(app_config, tracking_manager=tracking_manager)

    app_ui = AppUI(root, app_config, config_store, camera_manager, recorder_manager)

    def on_close() -> None:
        if not messagebox.askyesno(
            "Exit", "Stop all recording jobs and exit the program?"
        ):
            return
        names = recorder_manager.list_active()

        def finish() -> None:
            recorder_manager.shutdown()
            if tracking_manager is not None:
                tracking_manager.shutdown()
            camera_manager.shutdown()
            root.destroy()

        StopJobsDialog(root, recorder_manager).open(
            names,
            title="Exiting",
            on_done=finish,
            show_done_message=False,
        )

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
