import threading
import time
import tkinter as tk
import concurrent.futures
from tkinter import messagebox, ttk

import cv2
from PIL import Image, ImageTk

from app.config.models import CameraConfig
from app.core.camera_manager import CameraManager
from app.core.recorder_manager import RecorderManager
from app.ui.live_actions import open_live


class ManageView(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        camera_manager: CameraManager,
        recorder_manager: RecorderManager,
    ) -> None:
        super().__init__(parent)
        self.camera_manager = camera_manager
        self.recorder_manager = recorder_manager
        self._conn_status: dict[str, str] = {}
        self._conn_lock = threading.Lock()
        self._conn_stop = threading.Event()
        self._pending_checks: list[str] = []
        self._pending_lock = threading.Lock()
        self._check_thread: threading.Thread | None = None
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="All")
        self.preview_image = None

        self._build_ui()
        self._start_connection_checks()
        self._refresh_camera_list()

    def _build_ui(self) -> None:
        manager_bar = ttk.Frame(self)
        manager_bar.pack(fill=tk.X, padx=8, pady=(8, 6))

        ttk.Label(
            manager_bar, text="Manage Cameras", font=("Bai Jamjuree", 12, "bold")
        ).pack(side=tk.LEFT)

        ttk.Button(
            manager_bar,
            text="Add new camera",
            command=self._open_add_camera_dialog,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            manager_bar,
            text="Edit",
            command=self._open_edit_camera_dialog,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(
            manager_bar,
            text="Delete",
            command=self._delete_selected_camera,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(
            manager_bar,
            text="\u27f3 Refresh",
            command=self._refresh_connections,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=(0, 6))

        ttk.Label(toolbar, text="Search:").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(toolbar, textvariable=self.search_var, width=22).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Label(toolbar, text="Filter:").pack(side=tk.LEFT, padx=(0, 6))
        filter_box = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            values=["All", "Connected", "Recording", "Not connected", "Checking", "Idle"],
            state="readonly",
            width=16,
        )
        filter_box.pack(side=tk.LEFT)
        self.search_var.trace_add("write", lambda *_: self._refresh_camera_list())
        filter_box.bind("<<ComboboxSelected>>", lambda e: self._refresh_camera_list())

        self.empty_label = ttk.Label(
            self,
            text="No cameras yet. Please add a new camera.",
            font=("Bai Jamjuree", 12),
        )
        self.empty_label.pack_forget()

        self.tree = ttk.Treeview(
            self,
            columns=("name", "source", "link", "indicator", "status", "live"),
            show="headings",
            height=12,
        )
        self.tree.heading("name", text="Camera name")
        self.tree.heading("source", text="Source")
        self.tree.heading("link", text="RTSP link")
        self.tree.heading("indicator", text="State")
        self.tree.heading("status", text="Status")
        self.tree.heading("live", text="Live")
        self.tree.column("name", width=180, stretch=False)
        self.tree.column("source", width=90, stretch=False)
        self.tree.column("link", width=420, stretch=True)
        self.tree.column("indicator", width=60, anchor="center", stretch=False)
        self.tree.column("status", width=120, stretch=False)
        self.tree.column("live", width=60, anchor="center", stretch=False)
        self.tree.tag_configure("connected", background="#c9f7d6")
        self.tree.tag_configure("not_connected", background="#ffd6d6")
        self.tree.tag_configure("recording", background="#cfe8ff")
        self.tree.bind("<Button-1>", self._on_manage_tree_click)

    def _refresh_camera_list(self) -> None:
        selected = self._get_selected_camera_name()
        cameras = self.camera_manager.list_cameras()
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not cameras:
            self.tree.pack_forget()
            self.empty_label.pack(pady=(12, 8))
        else:
            self.empty_label.pack_forget()
            self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
            for cam in cameras:
                source = "Device" if cam.source == "device" else "RTSP"
                link = (
                    f"Device {cam.device_index}"
                    if cam.source == "device"
                    else cam.rtsp_url
                )
                status = self._get_status(cam.name)
                if not self._passes_filter(cam.name, status):
                    continue
                indicator = self._status_indicator(status)
                tags = ()
                if status == "recording":
                    tags = ("recording",)
                elif status == "connected":
                    tags = ("connected",)
                elif status == "not connected":
                    tags = ("not_connected",)
                merged_tags = list(tags)
                item_id = self.tree.insert(
                    "",
                    "end",
                    values=(cam.name, source, link, indicator, status, "\uf030"),
                    tags=tuple(merged_tags),
                )
                if selected and cam.name == selected:
                    self.tree.selection_set(item_id)

        self.after(1000, self._refresh_camera_list)

    def _open_add_camera_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Add Camera")
        dialog.configure(bg="white")
        dialog.grab_set()
        dialog.transient(self)
        dialog.resizable(False, False)

        width = 640
        height = 560
        x = self.winfo_rootx() + (self.winfo_width() - width) // 2
        y = self.winfo_rooty() + (self.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        style = ttk.Style(dialog)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Modal.TFrame", background="white")
        style.configure(
            "Modal.TLabel",
            background="white",
            foreground="#111827",
            font=("Bai Jamjuree", 12),
        )
        style.configure("Modal.TLabelframe", background="white")
        style.configure(
            "Modal.TLabelframe.Label",
            background="white",
            foreground="#111827",
            font=("Bai Jamjuree", 12, "bold"),
        )
        style.configure(
            "Modal.TRadiobutton",
            background="white",
            foreground="#111827",
            font=("Bai Jamjuree", 12),
        )
        style.configure("Modal.TButton", font=("Bai Jamjuree", 12))

        body = ttk.Frame(dialog, padding=16, style="Modal.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        source_var = tk.StringVar(value="rtsp")
        url_var = tk.StringVar()
        user_var = tk.StringVar()
        pass_var = tk.StringVar()
        name_var = tk.StringVar()
        device_var = tk.StringVar()

        source_row = ttk.Frame(body, style="Modal.TFrame")
        source_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Radiobutton(
            source_row,
            text="RTSP Stream",
            variable=source_var,
            value="rtsp",
            style="Modal.TRadiobutton",
        ).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Radiobutton(
            source_row,
            text="Device (Local Camera)",
            variable=source_var,
            value="device",
            style="Modal.TRadiobutton",
        ).pack(side=tk.LEFT)

        ttk.Separator(body).pack(fill=tk.X, pady=(0, 12))

        ttk.Label(body, text="Camera Name:", style="Modal.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        name_entry = ttk.Entry(body, textvariable=name_var, width=40)
        name_entry.pack(anchor="w", pady=(0, 12))

        rtsp_group = ttk.Labelframe(
            body, text="RTSP URL", padding=12, style="Modal.TLabelframe"
        )
        rtsp_group.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(rtsp_group, text="RTSP URL:", style="Modal.TLabel").grid(
            row=0, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        rtsp_url_entry = ttk.Entry(rtsp_group, textvariable=url_var, width=40)
        rtsp_url_entry.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(rtsp_group, text="Username:", style="Modal.TLabel").grid(
            row=1, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        user_entry = ttk.Entry(rtsp_group, textvariable=user_var, width=28)
        user_entry.grid(row=1, column=1, sticky="w", pady=6)

        ttk.Label(rtsp_group, text="Password:", style="Modal.TLabel").grid(
            row=2, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        pass_entry = ttk.Entry(rtsp_group, textvariable=pass_var, width=28, show="*")
        pass_entry.grid(row=2, column=1, sticky="w", pady=6)

        device_group = ttk.Labelframe(
            body, text="Select Device", padding=12, style="Modal.TLabelframe"
        )
        device_group.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(device_group, text="Device:", style="Modal.TLabel").grid(
            row=0, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        device_box = ttk.Combobox(
            device_group, textvariable=device_var, width=36, values=[]
        )
        device_box.grid(row=0, column=1, sticky="w", pady=6)

        def refresh_devices() -> None:
            devices = []
            for idx in range(2):
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    devices.append(f"Device {idx}")
                cap.release()
            if not devices:
                devices = ["No devices found"]
            device_box["values"] = devices
            device_var.set(devices[0])

        refresh_btn = ttk.Button(
            device_group, text="Refresh", command=refresh_devices, style="Modal.TButton"
        )
        refresh_btn.grid(row=0, column=2, padx=(8, 0))
        refresh_devices()

        def refresh_fields() -> None:
            is_device = source_var.get() == "device"
            rtsp_url_entry.configure(state="normal")
            user_entry.configure(state="normal")
            pass_entry.configure(state="normal")
            device_box.configure(state="normal")
            refresh_btn.configure(state="normal")
            if is_device:
                rtsp_url_entry.configure(state="disabled")
                user_entry.configure(state="disabled")
                pass_entry.configure(state="disabled")
            else:
                device_box.configure(state="disabled")
                refresh_btn.configure(state="disabled")

        def on_save() -> None:
            camera_name = name_var.get().strip()
            if source_var.get() == "device":
                selection = device_var.get().strip()
                if selection.startswith("No devices"):
                    messagebox.showwarning("Add camera", "No devices detected.")
                    return
                if selection.startswith("Device "):
                    index = int(selection.split(" ")[1])
                else:
                    index = 0
                if not camera_name:
                    camera_name = selection
                config = CameraConfig(
                    name=camera_name,
                    ip="",
                    port=0,
                    user="",
                    password="",
                    stream_path="",
                    source="device",
                    device_index=index,
                )
            else:
                rtsp_url = url_var.get().strip()
                if not rtsp_url:
                    messagebox.showwarning("Add camera", "RTSP URL is required.")
                    return
                if not camera_name:
                    messagebox.showwarning("Add camera", "Camera name is required.")
                    return
                config = CameraConfig(
                    name=camera_name,
                    ip="",
                    port=0,
                    user=user_var.get().strip(),
                    password=pass_var.get().strip(),
                    stream_path="",
                    source="rtsp",
                    rtsp_url=rtsp_url,
                )

            if messagebox.askyesno("Confirm", "Add this camera to the list?"):
                self.camera_manager.add_camera(config, start_worker=False)
                self._trigger_single_check(config.name)
                self._refresh_camera_list()
                dialog.destroy()

        source_var.trace_add("write", lambda *_: refresh_fields())
        refresh_fields()

        action_row = ttk.Frame(body, style="Modal.TFrame")
        action_row.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(
            action_row, text="Save", command=on_save, style="Modal.TButton"
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(
            action_row, text="Cancel", command=dialog.destroy, style="Modal.TButton"
        ).pack(side=tk.LEFT)

    def _open_edit_camera_dialog(self) -> None:
        name = self._get_selected_camera_name()
        if not name:
            messagebox.showwarning("Edit camera", "Please select a camera.")
            return
        cam = self.camera_manager.get_camera(name)
        dialog = tk.Toplevel(self)
        dialog.title("Edit Camera")
        dialog.configure(bg="white")
        dialog.grab_set()
        dialog.transient(self)
        dialog.resizable(False, False)

        width = 640
        height = 560
        x = self.winfo_rootx() + (self.winfo_width() - width) // 2
        y = self.winfo_rooty() + (self.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        style = ttk.Style(dialog)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Modal.TFrame", background="white")
        style.configure(
            "Modal.TLabel",
            background="white",
            foreground="#111827",
            font=("Bai Jamjuree", 12),
        )
        style.configure("Modal.TLabelframe", background="white")
        style.configure(
            "Modal.TLabelframe.Label",
            background="white",
            foreground="#111827",
            font=("Bai Jamjuree", 12, "bold"),
        )
        style.configure(
            "Modal.TRadiobutton",
            background="white",
            foreground="#111827",
            font=("Bai Jamjuree", 12),
        )
        style.configure("Modal.TButton", font=("Bai Jamjuree", 12))

        body = ttk.Frame(dialog, padding=16, style="Modal.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        source_var = tk.StringVar(value=cam.source)
        url_var = tk.StringVar(value=cam.rtsp_url)
        user_var = tk.StringVar(value=cam.user)
        pass_var = tk.StringVar(value=cam.password)
        name_var = tk.StringVar(value=cam.name)
        device_var = tk.StringVar(value=f"Device {cam.device_index}")

        source_row = ttk.Frame(body, style="Modal.TFrame")
        source_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Radiobutton(
            source_row,
            text="RTSP Stream",
            variable=source_var,
            value="rtsp",
            style="Modal.TRadiobutton",
        ).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Radiobutton(
            source_row,
            text="Device (Local Camera)",
            variable=source_var,
            value="device",
            style="Modal.TRadiobutton",
        ).pack(side=tk.LEFT)

        ttk.Separator(body).pack(fill=tk.X, pady=(0, 12))

        ttk.Label(body, text="Camera Name:", style="Modal.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        ttk.Entry(body, textvariable=name_var, width=40).pack(anchor="w", pady=(0, 12))

        rtsp_group = ttk.Labelframe(
            body, text="RTSP URL", padding=12, style="Modal.TLabelframe"
        )
        rtsp_group.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(rtsp_group, text="RTSP URL:", style="Modal.TLabel").grid(
            row=0, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        rtsp_url_entry = ttk.Entry(rtsp_group, textvariable=url_var, width=40)
        rtsp_url_entry.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(rtsp_group, text="Username:", style="Modal.TLabel").grid(
            row=1, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        user_entry = ttk.Entry(rtsp_group, textvariable=user_var, width=28)
        user_entry.grid(row=1, column=1, sticky="w", pady=6)

        ttk.Label(rtsp_group, text="Password:", style="Modal.TLabel").grid(
            row=2, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        pass_entry = ttk.Entry(rtsp_group, textvariable=pass_var, width=28, show="*")
        pass_entry.grid(row=2, column=1, sticky="w", pady=6)

        device_group = ttk.Labelframe(
            body, text="Select Device", padding=12, style="Modal.TLabelframe"
        )
        device_group.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(device_group, text="Device:", style="Modal.TLabel").grid(
            row=0, column=0, sticky="w", pady=6, padx=(0, 8)
        )
        device_box = ttk.Combobox(
            device_group, textvariable=device_var, width=36, values=[]
        )
        device_box.grid(row=0, column=1, sticky="w", pady=6)

        def refresh_devices() -> None:
            devices = []
            for idx in range(2):
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    devices.append(f"Device {idx}")
                cap.release()
            if not devices:
                devices = ["No devices found"]
            device_box["values"] = devices
            if device_var.get() not in devices:
                device_var.set(devices[0])

        ttk.Button(device_group, text="Refresh", command=refresh_devices, style="Modal.TButton").grid(
            row=0, column=2, padx=(8, 0)
        )
        refresh_devices()

        def refresh_fields() -> None:
            is_device = source_var.get() == "device"
            rtsp_url_entry.configure(state="normal")
            user_entry.configure(state="normal")
            pass_entry.configure(state="normal")
            device_box.configure(state="normal")
            if is_device:
                rtsp_url_entry.configure(state="disabled")
                user_entry.configure(state="disabled")
                pass_entry.configure(state="disabled")
            else:
                device_box.configure(state="disabled")

        def on_save() -> None:
            new_name = name_var.get().strip()
            if not new_name:
                messagebox.showwarning("Edit camera", "Camera name is required.")
                return
            if source_var.get() == "device":
                selection = device_var.get().strip()
                if selection.startswith("No devices"):
                    messagebox.showwarning("Edit camera", "No devices detected.")
                    return
                if selection.startswith("Device "):
                    index = int(selection.split(" ")[1])
                else:
                    index = 0
                new_config = CameraConfig(
                    name=new_name,
                    ip="",
                    port=0,
                    user="",
                    password="",
                    stream_path="",
                    source="device",
                    device_index=index,
                )
            else:
                rtsp_url = url_var.get().strip()
                if not rtsp_url:
                    messagebox.showwarning("Edit camera", "RTSP URL is required.")
                    return
                new_config = CameraConfig(
                    name=new_name,
                    ip="",
                    port=0,
                    user=user_var.get().strip(),
                    password=pass_var.get().strip(),
                    stream_path="",
                    source="rtsp",
                    rtsp_url=rtsp_url,
                )
            self.camera_manager.update_camera(name, new_config, start_worker=False)
            self._trigger_single_check(new_name)
            self._refresh_camera_list()
            dialog.destroy()

        source_var.trace_add("write", lambda *_: refresh_fields())
        refresh_fields()

        action_row = ttk.Frame(body, style="Modal.TFrame")
        action_row.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(action_row, text="Save", command=on_save, style="Modal.TButton").pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Button(action_row, text="Cancel", command=dialog.destroy, style="Modal.TButton").pack(
            side=tk.LEFT
        )

    def _delete_selected_camera(self) -> None:
        name = self._get_selected_camera_name()
        if not name:
            messagebox.showwarning("Delete camera", "Please select a camera.")
            return
        if messagebox.askyesno("Delete camera", f"Delete {name}?"):
            self.camera_manager.remove_camera(name)
            self._refresh_camera_list()
            with self._conn_lock:
                self._conn_status.pop(name, None)

    def _refresh_connections(self) -> None:
        self._enqueue_checks([c.name for c in self.camera_manager.list_cameras()])
        messagebox.showinfo("Refresh connection", "Checking camera connections...")

    def _get_selected_camera_name(self) -> str | None:
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], "values")
        return values[0] if values else None


    def _start_connection_checks(self) -> None:
        self._enqueue_checks([c.name for c in self.camera_manager.list_cameras()])

    def _trigger_single_check(self, name: str) -> None:
        self._enqueue_checks([name])

    def _enqueue_checks(self, names: list[str]) -> None:
        with self._pending_lock:
            for name in names:
                if name not in self._pending_checks:
                    self._pending_checks.append(name)
        if self._check_thread is None or not self._check_thread.is_alive():
            self._check_thread = threading.Thread(
                target=self._run_check_queue, daemon=True
            )
            self._check_thread.start()

    def _run_check_queue(self) -> None:
        with self._pending_lock:
            names = list(self._pending_checks)
            self._pending_checks.clear()
        cameras = []
        for name in names:
            try:
                cam = self.camera_manager.get_camera(name)
            except KeyError:
                continue
            self._set_status(cam.name, "checking")
            cameras.append(cam)
        if not cameras:
            return
        max_workers = min(8, len(cameras))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self._probe_camera, cam): cam for cam in cameras}
            for future, cam in future_map.items():
                ok = future.result()
                self._set_status(cam.name, "connected" if ok else "not connected")

    def _probe_camera(self, cam: CameraConfig) -> bool:
        cap = None
        try:
            if cam.source == "device":
                cap = cv2.VideoCapture(cam.device_index)
            else:
                cap = cv2.VideoCapture(cam.rtsp_url)
            if not cap.isOpened():
                return False
            ok, frame = cap.read()
            return bool(ok and frame is not None)
        finally:
            if cap is not None:
                cap.release()

    def _set_status(self, name: str, status: str) -> None:
        with self._conn_lock:
            self._conn_status[name] = status
        try:
            runtime = self.camera_manager.get_runtime(name)
            runtime.status = status
        except Exception:
            pass

    def _get_status(self, name: str) -> str:
        if name in self.recorder_manager.list_active():
            return "recording"
        with self._conn_lock:
            return self._conn_status.get(name, "idle")

    def _status_indicator(self, status: str) -> str:
        if status == "recording":
            return "REC"
        if status == "connected":
            return "\u2714"
        if status == "not connected":
            return "\u2716"
        if status == "checking":
            return "\u27f3"
        return "\u25cf"

    def _passes_filter(self, name: str, status: str) -> bool:
        text = self.search_var.get().strip().lower()
        if text and text not in name.lower():
            return False
        filt = self.filter_var.get()
        if filt == "All":
            return True
        if filt == "Connected":
            return status == "connected"
        if filt == "Recording":
            return status == "recording"
        if filt == "Not connected":
            return status == "not connected"
        if filt == "Checking":
            return status == "checking"
        if filt == "Idle":
            return status == "idle"
        return True
    def _on_manage_tree_click(self, event: tk.Event) -> None:
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            self.tree.selection_remove(self.tree.selection())
            return
        column = self.tree.identify_column(event.x)
        if column == "#6":
            values = self.tree.item(row_id, "values")
            if values:
                name = values[0]
                camera = self.camera_manager.get_camera(name)
                open_live(self, camera)
