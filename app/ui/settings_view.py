from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.config.models import AppConfig
from app.config.store import ConfigStore
from app.core.camera_manager import CameraManager
from app.utils.paths import set_files_dir


class SettingsView(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        app_config: AppConfig,
        config_store: ConfigStore,
        camera_manager: CameraManager,
    ) -> None:
        super().__init__(parent)
        self.app_config = app_config
        self.config_store = config_store
        self.camera_manager = camera_manager

        self._vars: dict[str, tk.Variable] = {}
        self._build_ui()
        self._load_current()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        base_bg = style.lookup("App.TFrame", "background") or "#f7f4ef"
        style.configure("Settings.TFrame", background=base_bg)
        style.configure("Settings.TNotebook", background=base_bg, borderwidth=0)
        style.configure("Settings.TNotebook.Tab", font=("Bai Jamjuree", 11, "bold"), padding=(12, 6))
        style.configure("Settings.TLabelframe", background=base_bg)
        style.configure(
            "Settings.TLabelframe.Label",
            background=base_bg,
            font=("Bai Jamjuree", 11, "bold"),
            foreground="#111827",
        )
        style.configure("Settings.TEntry", font=("Bai Jamjuree", 12))
        style.configure("Settings.TCheckbutton", font=("Bai Jamjuree", 12))

        header = ttk.Frame(self, style="App.TFrame")
        header.pack(fill=tk.X, padx=8, pady=(10, 6))
        ttk.Label(header, text="Settings", style="App.Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(
            header,
            text="Save settings",
            style="App.Toolbar.AccentText.TButton",
            command=self._save_settings,
        ).pack(side=tk.RIGHT)

        container = ttk.Frame(self, style="Settings.TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 10))

        notebook = ttk.Notebook(container, style="Settings.TNotebook")
        notebook.pack(fill=tk.BOTH, expand=True)

        storage_tab = ttk.Frame(notebook, style="Settings.TFrame", padding=12)
        recording_tab = ttk.Frame(notebook, style="Settings.TFrame", padding=12)
        camera_tab = ttk.Frame(notebook, style="Settings.TFrame", padding=12)
        detect_tab = ttk.Frame(notebook, style="Settings.TFrame", padding=12)
        tracking_tab = ttk.Frame(notebook, style="Settings.TFrame", padding=12)

        notebook.add(storage_tab, text="Storage")
        notebook.add(recording_tab, text="Recording")
        notebook.add(camera_tab, text="Camera")
        notebook.add(detect_tab, text="Detection")
        notebook.add(tracking_tab, text="Tracking")

        self._build_storage_section(storage_tab)
        self._build_recording_section(recording_tab)
        self._build_camera_section(camera_tab)
        self._build_yolo_section(detect_tab)
        self._build_tracking_section(tracking_tab)

    def _build_storage_section(self, parent: tk.Misc) -> None:
        box = ttk.Labelframe(parent, text="Storage & Retention", padding=10, style="Settings.TLabelframe")
        box.pack(fill=tk.X, pady=(0, 10))
        self._add_path_row(
            box,
            "Storage folder",
            "files_dir",
            browse_title="Choose storage folder",
            choose_dir=True,
        )
        self._add_int_row(box, "Days keep", "days_keep")
        self._add_int_row(box, "Min free GB", "min_free_gb")
        self._add_bool_row(box, "Enable disk check", "enable_disk_check")
        self._add_bool_row(box, "Enable disk quota", "enable_disk_quota")
        self._add_bool_row(box, "Enable retention", "enable_retention")

    def _build_recording_section(self, parent: tk.Misc) -> None:
        box = ttk.Labelframe(parent, text="Recording", padding=10, style="Settings.TLabelframe")
        box.pack(fill=tk.X, pady=(0, 10))
        self._add_int_row(box, "Record FPS", "fps_record")
        self._add_int_row(box, "Detect FPS", "fps_detect")
        self._add_bool_row(box, "Enable motion (offline)", "motion_offline")

    def _build_camera_section(self, parent: tk.Misc) -> None:
        box = ttk.Labelframe(parent, text="Camera Connection", padding=10, style="Settings.TLabelframe")
        box.pack(fill=tk.X, pady=(0, 10))
        self._add_float_row(box, "Reconnect min (s)", "cam_reconnect_min_s")
        self._add_float_row(box, "Reconnect max (s)", "cam_reconnect_max_s")
        self._add_float_row(box, "Stale timeout (s)", "cam_stale_s")

    def _build_yolo_section(self, parent: tk.Misc) -> None:
        box = ttk.Labelframe(parent, text="YOLO Detection", padding=10, style="Settings.TLabelframe")
        box.pack(fill=tk.X, pady=(0, 10))
        self._add_path_row(
            box,
            "Model path",
            "yolo.model_path",
            browse_title="Select YOLO model",
            choose_dir=False,
        )
        self._add_float_row(box, "Confidence", "yolo.conf_thres")
        self._add_int_row(box, "Start frames", "yolo.start_frames")
        self._add_int_row(box, "Stop seconds", "yolo.stop_seconds")

    def _build_tracking_section(self, parent: tk.Misc) -> None:
        box = ttk.Labelframe(parent, text="Tracking", padding=10, style="Settings.TLabelframe")
        box.pack(fill=tk.X, pady=(0, 10))
        self._add_bool_row(box, "Enable tracking", "tracking.enabled")
        self._add_path_row(
            box,
            "Model path",
            "tracking.model_path",
            browse_title="Select tracking model",
            choose_dir=False,
        )
        self._add_float_row(box, "Confidence", "tracking.conf_thres")
        self._add_bool_row(box, "Use GPU", "tracking.use_gpu")

    def _add_row(self, parent: tk.Misc, row: int, label: str, widget: tk.Widget) -> None:
        ttk.Label(parent, text=label, style="App.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=4
        )
        widget.grid(row=row, column=1, sticky="w", pady=4)
        parent.columnconfigure(1, weight=0)

    def _add_path_row(
        self,
        parent: tk.Misc,
        label: str,
        key: str,
        browse_title: str,
        choose_dir: bool = False,
    ) -> None:
        var = tk.StringVar()
        self._vars[key] = var
        row = parent.grid_size()[1]
        entry = ttk.Entry(parent, textvariable=var, width=32, style="Settings.TEntry")
        self._add_row(parent, row, label, entry)
        browse = ttk.Button(
            parent,
            text="Browse",
            style="App.Toolbar.TButton",
            command=lambda: self._browse_path(var, browse_title, choose_dir),
        )
        browse.grid(row=row, column=2, sticky="e", padx=(8, 0), pady=4)
        parent.columnconfigure(2, weight=0)

    def _add_int_row(self, parent: tk.Misc, label: str, key: str) -> None:
        var = tk.StringVar()
        self._vars[key] = var
        row = parent.grid_size()[1]
        entry = ttk.Entry(parent, textvariable=var, width=10, style="Settings.TEntry")
        self._add_row(parent, row, label, entry)

    def _add_float_row(self, parent: tk.Misc, label: str, key: str) -> None:
        var = tk.StringVar()
        self._vars[key] = var
        row = parent.grid_size()[1]
        entry = ttk.Entry(parent, textvariable=var, width=10, style="Settings.TEntry")
        self._add_row(parent, row, label, entry)

    def _add_bool_row(self, parent: tk.Misc, label: str, key: str) -> None:
        var = tk.BooleanVar()
        self._vars[key] = var
        row = parent.grid_size()[1]
        cb = ttk.Checkbutton(parent, variable=var, style="Settings.TCheckbutton")
        self._add_row(parent, row, label, cb)

    def _browse_path(self, var: tk.StringVar, title: str, choose_dir: bool) -> None:
        if choose_dir:
            selected = filedialog.askdirectory(title=title, mustexist=False)
        else:
            selected = filedialog.askopenfilename(title=title)
        if selected:
            var.set(selected)

    def _load_current(self) -> None:
        self._vars["files_dir"].set(self.app_config.files_dir)
        self._vars["days_keep"].set(str(self.app_config.days_keep))
        self._vars["min_free_gb"].set(str(self.app_config.min_free_gb))
        self._vars["enable_disk_check"].set(bool(self.app_config.enable_disk_check))
        self._vars["enable_disk_quota"].set(bool(self.app_config.enable_disk_quota))
        self._vars["enable_retention"].set(bool(self.app_config.enable_retention))
        self._vars["fps_record"].set(str(self.app_config.fps_record))
        self._vars["fps_detect"].set(str(self.app_config.fps_detect))
        self._vars["motion_offline"].set(bool(self.app_config.motion_offline))
        self._vars["cam_reconnect_min_s"].set(str(self.app_config.cam_reconnect_min_s))
        self._vars["cam_reconnect_max_s"].set(str(self.app_config.cam_reconnect_max_s))
        self._vars["cam_stale_s"].set(str(self.app_config.cam_stale_s))
        self._vars["yolo.model_path"].set(self.app_config.yolo.model_path)
        self._vars["yolo.conf_thres"].set(str(self.app_config.yolo.conf_thres))
        self._vars["yolo.start_frames"].set(str(self.app_config.yolo.start_frames))
        self._vars["yolo.stop_seconds"].set(str(self.app_config.yolo.stop_seconds))
        self._vars["tracking.enabled"].set(bool(self.app_config.tracking.enabled))
        self._vars["tracking.model_path"].set(self.app_config.tracking.model_path)
        self._vars["tracking.conf_thres"].set(str(self.app_config.tracking.conf_thres))
        self._vars["tracking.use_gpu"].set(bool(self.app_config.tracking.use_gpu))

    def _save_settings(self) -> None:
        try:
            self.app_config.files_dir = str(self._vars["files_dir"].get()).strip() or "Files"
            self.app_config.days_keep = int(self._vars["days_keep"].get())
            self.app_config.min_free_gb = int(self._vars["min_free_gb"].get())
            self.app_config.enable_disk_check = bool(self._vars["enable_disk_check"].get())
            self.app_config.enable_disk_quota = bool(self._vars["enable_disk_quota"].get())
            self.app_config.enable_retention = bool(self._vars["enable_retention"].get())
            self.app_config.fps_record = int(self._vars["fps_record"].get())
            self.app_config.fps_detect = int(self._vars["fps_detect"].get())
            self.app_config.motion_offline = bool(self._vars["motion_offline"].get())
            self.app_config.cam_reconnect_min_s = float(self._vars["cam_reconnect_min_s"].get())
            self.app_config.cam_reconnect_max_s = float(self._vars["cam_reconnect_max_s"].get())
            self.app_config.cam_stale_s = float(self._vars["cam_stale_s"].get())
            self.app_config.yolo.model_path = str(
                self._vars["yolo.model_path"].get()
            ).strip()
            self.app_config.yolo.conf_thres = float(self._vars["yolo.conf_thres"].get())
            self.app_config.yolo.start_frames = int(self._vars["yolo.start_frames"].get())
            self.app_config.yolo.stop_seconds = int(self._vars["yolo.stop_seconds"].get())
            self.app_config.tracking.enabled = bool(
                self._vars["tracking.enabled"].get()
            )
            self.app_config.tracking.model_path = str(
                self._vars["tracking.model_path"].get()
            ).strip()
            self.app_config.tracking.conf_thres = float(
                self._vars["tracking.conf_thres"].get()
            )
            self.app_config.tracking.use_gpu = bool(
                self._vars["tracking.use_gpu"].get()
            )
        except ValueError as exc:
            messagebox.showerror("Invalid settings", f"Please check values.\n{exc}")
            return

        set_files_dir(self.app_config.files_dir)
        self.config_store.save(self.app_config, self.camera_manager.list_cameras())
        messagebox.showinfo("Settings saved", "Configuration saved successfully.")
