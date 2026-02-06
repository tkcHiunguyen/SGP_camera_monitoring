import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import ctypes
import time
import os

from app.config.store import ConfigStore
from app.core.camera_manager import CameraManager
from app.core.frame_store import FrameStore
from app.core.recorder_manager import RecorderManager
from app.core.tracking_manager import TrackingManager
from app.core.stream_manager import StreamManager
from app.ui.app_ui import AppUI
from app.ui.stop_jobs_dialog import StopJobsDialog
from app.utils.logging_setup import setup_logging
from app.utils.paths import set_files_dir

APP_NAME = "Camera Recorder"
DEFAULT_FFMPEG_OPTIONS = "rtsp_flags;prefer_tcp;timeout;60000000;buffer_size;256000"


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

    os.environ.setdefault(
        "OPENCV_FFMPEG_CAPTURE_OPTIONS",
        "rtsp_transport;udp;fflags;nobuffer;flags;low_delay;max_delay;500000;buffer_size;256000;stimeout;5000000",
    )

    config_store = ConfigStore()
    app_config, cameras = config_store.load()
    if app_config.files_dir:
        set_files_dir(Path(app_config.files_dir))
    setup_logging()

    def resource_path(rel_path: str) -> Path:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return base / rel_path

    root = tk.Tk()
    try:
        icon_png = resource_path("assets/logo/logo_cam.png")
        if icon_png.exists():
            icon_img = tk.PhotoImage(file=str(icon_png))
            root.iconphoto(True, icon_img)
        icon_ico = resource_path("assets/logo/logo_cam.ico")
        if icon_ico.exists():
            root.iconbitmap(str(icon_ico))
    except Exception:
        pass
    frame_store = FrameStore()
    camera_manager = CameraManager(config_store, frame_store)
    camera_manager.load_from_config(cameras, start_workers=False)
    stream_manager = StreamManager(camera_manager, idle_timeout_s=10.0)
    tracking_manager = None
    if app_config.tracking.enabled:
        tracking_manager = TrackingManager(
            Path(app_config.tracking.model_path),
            conf_thres=app_config.tracking.conf_thres,
            use_gpu=app_config.tracking.use_gpu,
        )
    last_disk_warn = {"ts": 0.0}

    def on_disk_warning(free_gb: float, min_gb: float) -> None:
        now = time.time()
        if now - last_disk_warn["ts"] < 30.0:
            return
        last_disk_warn["ts"] = now

        def _show() -> None:
            messagebox.showwarning(
                "Low disk space",
                f"Free space {free_gb:.2f} GB is below minimum {min_gb:.2f} GB.",
            )

        root.after(0, _show)

    recorder_manager = RecorderManager(
        app_config,
        tracking_manager=tracking_manager,
        on_disk_warning=on_disk_warning,
        stream_manager=stream_manager,
        frame_store=frame_store,
    )

    app_ui = AppUI(
        root,
        app_config,
        config_store,
        camera_manager,
        recorder_manager,
        stream_manager,
        frame_store,
    )

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
            stream_manager.shutdown()
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
