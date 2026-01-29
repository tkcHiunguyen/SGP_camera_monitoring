import os
import tkinter as tk
from tkinter import ttk

from app.config.models import AppConfig
from app.config.store import ConfigStore
from app.core.camera_manager import CameraManager
from app.core.recorder_manager import RecorderManager
from app.ui.edit_view import EditView
from app.ui.live_view import LiveView
from app.ui.manage_view import ManageView
from app.ui.recorder_view import RecorderView


class AppUI:
    def __init__(
        self,
        root: tk.Tk,
        app_config: AppConfig,
        config_store: ConfigStore,
        camera_manager: CameraManager,
        recorder_manager: RecorderManager,
    ) -> None:
        self.root = root
        self.app_config = app_config
        self.config_store = config_store
        self.camera_manager = camera_manager
        self.recorder_manager = recorder_manager

        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "rtsp_flags;prefer_tcp;timeout;10000000;buffer_size;256000",
        )

        self._load_fonts()
        self._build_ui()

    def _load_fonts(self) -> None:
        import ctypes
        from pathlib import Path

        base = Path(__file__).resolve().parents[2] / "assets" / "fonts"
        font_paths = [
            base / "BaiJamjuree-Regular.ttf",
            base / "BaiJamjuree-SemiBold.ttf",
            base / "fontawesome" / "fa-solid-900.ttf",
            base / "fontawesome" / "fa-regular-400.ttf",
            base / "fontawesome" / "fa-brands-400.ttf",
            base / "fontawesome" / "fa-v4compatibility.ttf",
        ]
        gdi32 = ctypes.windll.gdi32
        for font_path in font_paths:
            if font_path.exists():
                gdi32.AddFontResourceExW(str(font_path), 0x10, 0)

    def _build_ui(self) -> None:
        self.root.title("Camera Recorder")
        width = 980
        height = 560
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2) - 100
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        container = ttk.Frame(self.root, padding=0)
        container.pack(fill=tk.BOTH, expand=True)

        self.header_frame = ttk.Frame(container)
        self.header_frame.pack(fill=tk.X)
        ttk.Label(
            self.header_frame, text="\uf030", font=("Font Awesome 6 Free Solid", 16)
        ).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Label(
            self.header_frame, text="Camera Recorder", font=("Bai Jamjuree", 18, "bold")
        ).pack(side=tk.LEFT)

        self.menu_bar = ttk.Frame(container)
        self.menu_bar.pack(fill=tk.X, pady=(10, 12))
        style = ttk.Style(self.menu_bar)
        style.configure("MenuBar.TFrame", background="#c9d9ee")
        self.menu_bar.configure(style="MenuBar.TFrame")

        self.active_tab = tk.StringVar(value="Manage")
        ttk.Button(
            self.menu_bar,
            text="Manage Cameras",
            command=lambda: self._set_tab("Manage"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            self.menu_bar,
            text="Recorder",
            command=lambda: self._set_tab("Recorder"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            self.menu_bar,
            text="Liveview",
            command=lambda: self._set_tab("Liveview"),
        ).pack(side=tk.LEFT)
        ttk.Button(
            self.menu_bar,
            text="Edit",
            command=lambda: self._set_tab("Edit"),
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.content = ttk.Frame(container)
        self.content.pack(fill=tk.BOTH, expand=True)

        self.manage_view = ManageView(
            self.content, self.camera_manager, self.recorder_manager
        )
        self.recorder_view = RecorderView(
            self.content, self.camera_manager, self.recorder_manager
        )
        self.live_view = LiveView(
            self.content,
            self.camera_manager,
            self.recorder_manager,
            on_fullscreen_toggle=self._on_liveview_fullscreen,
        )
        self.edit_view = EditView(self.content)

        self.manage_view.pack(fill=tk.BOTH, expand=True)

    def _set_tab(self, tab_name: str) -> None:
        self.manage_view.pack_forget()
        self.recorder_view.pack_forget()
        self.live_view.pack_forget()
        self.edit_view.pack_forget()
        if tab_name == "Manage":
            self.manage_view.pack(fill=tk.BOTH, expand=True)
        elif tab_name == "Recorder":
            self.recorder_view.pack(fill=tk.BOTH, expand=True)
        elif tab_name == "Edit":
            self.edit_view.pack(fill=tk.BOTH, expand=True)
        else:
            self.live_view.pack(fill=tk.BOTH, expand=True)

    def _on_liveview_fullscreen(self, fullscreen: bool) -> None:
        if fullscreen:
            self.root.attributes("-fullscreen", True)
            self.header_frame.pack_forget()
            self.menu_bar.pack_forget()
        else:
            self.root.attributes("-fullscreen", False)
            self.header_frame.pack(before=self.content, fill=tk.X)
            self.menu_bar.pack(before=self.content, fill=tk.X, pady=(10, 12))
