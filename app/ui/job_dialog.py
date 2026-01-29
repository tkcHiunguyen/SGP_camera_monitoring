import tkinter as tk
from tkinter import messagebox, ttk

from app.core.camera_manager import CameraManager
from app.core.recorder_manager import RecorderManager


class JobDialog:
    def __init__(
        self,
        parent: tk.Misc,
        camera_manager: CameraManager,
        recorder_manager: RecorderManager,
    ) -> None:
        self.parent = parent
        self.camera_manager = camera_manager
        self.recorder_manager = recorder_manager

    def open(self) -> None:
        dialog = tk.Toplevel(self.parent)
        dialog.title("Create Recorder Job")
        dialog.configure(bg="white")
        dialog.grab_set()
        dialog.transient(self.parent)
        dialog.resizable(False, False)

        width = 560
        height = 420
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - width) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        style = ttk.Style(dialog)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Job.TFrame", background="white")
        style.configure(
            "Job.TLabel",
            background="white",
            foreground="#111827",
            font=("Bai Jamjuree", 12),
        )
        style.configure("Job.TButton", font=("Bai Jamjuree", 12))
        style.configure(
            "Job.TCombobox",
            padding=(8, 6),
            font=("Bai Jamjuree", 13),
        )
        style.map(
            "Job.TCombobox",
            fieldbackground=[("readonly", "#f3f4f6")],
            background=[("readonly", "#f3f4f6")],
        )
        dialog.option_add("*TCombobox*Listbox.font", ("Bai Jamjuree", 12))
        style.configure("Job.TNotebook", background="white")
        style.configure("Job.TNotebook.Tab", font=("Bai Jamjuree", 11, "bold"))

        body = ttk.Frame(dialog, padding=16, style="Job.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        cameras = self.camera_manager.list_cameras()
        cam_names = [
            c.name
            for c in cameras
            if self._is_connected(self._get_status(c.name))
            and not self._is_recording(c.name)
        ]

        tabs = ttk.Notebook(body, style="Job.TNotebook")
        tabs.pack(fill=tk.BOTH, expand=True)

        single_tab = ttk.Frame(tabs, padding=12, style="Job.TFrame")
        multi_tab = ttk.Frame(tabs, padding=12, style="Job.TFrame")
        tabs.add(single_tab, text="Single")
        tabs.add(multi_tab, text="Multi")
        multi_tab.columnconfigure(0, weight=1)
        multi_tab.rowconfigure(1, weight=1)

        ttk.Label(single_tab, text="Select camera:", style="Job.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        cam_var = tk.StringVar(value=cam_names[0] if cam_names else "")
        cam_box = ttk.Combobox(
            single_tab,
            textvariable=cam_var,
            values=cam_names,
            width=30,
            style="Job.TCombobox",
        )
        cam_box.pack(anchor="w", pady=(0, 12))

        ttk.Label(single_tab, text="Output:", style="Job.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        ttk.Label(
            single_tab,
            text="Files/Media/Videos/<Year>/<Month>/<Day>/<CameraName>/",
            style="Job.TLabel",
        ).pack(anchor="w")

        multi_header = ttk.Frame(multi_tab, style="Job.TFrame")
        multi_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        multi_header.columnconfigure(2, weight=1)

        ttk.Label(multi_header, text="Select cameras:", style="Job.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        list_frame = ttk.Frame(multi_tab, style="Job.TFrame")
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        cam_list = tk.Listbox(
            list_frame,
            selectmode="multiple",
            height=10,
            exportselection=False,
            font=("Bai Jamjuree", 12),
            selectbackground="#c7d2fe",
            selectforeground="#111827",
            activestyle="none",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#e5e7eb",
        )
        cam_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=cam_list.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        cam_list.configure(yscrollcommand=scroll.set)

        for cam in cameras:
            if self._is_connected(self._get_status(cam.name)) and not self._is_recording(
                cam.name
            ):
                cam_list.insert(tk.END, cam.name)

        ttk.Button(
            multi_header,
            text="Select all",
            command=lambda: cam_list.select_set(0, tk.END),
            style="Job.TButton",
            width=10,
        ).grid(row=0, column=1, sticky="e", padx=(8, 6))
        ttk.Button(
            multi_header,
            text="Clear",
            command=lambda: cam_list.selection_clear(0, tk.END),
            style="Job.TButton",
            width=8,
        ).grid(row=0, column=2, sticky="e")

        info = ttk.Label(
            multi_tab,
            text="Tip: Choose multiple cameras to start recording together.",
            style="Job.TLabel",
        )
        info.grid(row=2, column=0, sticky="w")

        def on_create_single() -> None:
            name = cam_var.get().strip()
            if not name:
                messagebox.showwarning("Create job", "Please select a camera.")
                return
            camera = self.camera_manager.get_camera(name)
            try:
                self.recorder_manager.start(camera)
            except Exception as exc:
                messagebox.showerror("Create job", str(exc))
                return
            dialog.destroy()

        def on_create_multi() -> None:
            selections = cam_list.curselection()
            if not selections:
                messagebox.showwarning("Create jobs", "Please select at least one camera.")
                return
            failed = []
            for idx in selections:
                name = cam_list.get(idx)
                camera = self.camera_manager.get_camera(name)
                try:
                    self.recorder_manager.start(camera)
                except Exception as exc:
                    failed.append(f"{name}: {exc}")
            if failed:
                messagebox.showwarning("Create jobs", "\n".join(failed))
            dialog.destroy()

        single_actions = ttk.Frame(single_tab, style="Job.TFrame")
        single_actions.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(
            single_actions, text="Save", command=on_create_single, style="Job.TButton"
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(
            single_actions, text="Cancel", command=dialog.destroy, style="Job.TButton"
        ).pack(side=tk.LEFT)

        multi_actions = ttk.Frame(multi_tab, style="Job.TFrame")
        multi_actions.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(
            multi_actions, text="Save", command=on_create_multi, style="Job.TButton"
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(
            multi_actions, text="Cancel", command=dialog.destroy, style="Job.TButton"
        ).pack(side=tk.LEFT)

    def _get_status(self, name: str) -> str:
        try:
            runtime = self.camera_manager.get_runtime(name)
            return runtime.status
        except Exception:
            return ""

    def _is_connected(self, status: str) -> bool:
        value = status.lower()
        return value in {"connected", "online"}

    def _is_recording(self, name: str) -> bool:
        return name in self.recorder_manager.list_active()
