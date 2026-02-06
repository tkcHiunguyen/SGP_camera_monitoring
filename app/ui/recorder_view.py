from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk

from app.config.models import CameraConfig
from app.core.camera_manager import CameraManager
from app.core.recorder_manager import RecorderManager
from app.core.stream_manager import StreamManager
from app.core.frame_store import FrameStore
from app.ui.job_dialog import JobDialog
from app.ui.stop_jobs_dialog import StopJobsDialog
from app.ui.live_actions import open_live
from app.ui.widgets.empty_state import EmptyState


class RecorderView(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        camera_manager: CameraManager,
        recorder_manager: RecorderManager,
        stream_manager: StreamManager,
        frame_store: FrameStore,
    ) -> None:
        super().__init__(parent)
        self.camera_manager = camera_manager
        self.recorder_manager = recorder_manager
        self.stream_manager = stream_manager
        self.frame_store = frame_store
        self._job_cards: dict[str, dict[str, object]] = {}
        self._selected_jobs: set[str] = set()
        self._layout_state = {"cols": 0, "count": 0, "width": 0}
        self._build_ui()
        self._refresh_jobs()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.configure("Recorder.CardHeader.TFrame", background="#dbe4f0")
        style.configure(
            "Recorder.CardHeader.TLabel",
            background="#dbe4f0",
            font=("Bai Jamjuree", 12, "bold"),
        )
        style.configure(
            "Recorder.CardHeaderStatus.TLabel",
            background="#dbe4f0",
            font=("Bai Jamjuree", 11),
            foreground="#16a34a",
        )
        style.configure(
            "Recorder.Motion.TCheckbutton",
            font=("Bai Jamjuree", 12, "bold"),
        )
        style.configure("Recorder.CardHeader.TCheckbutton", background="#dbe4f0")

        recorder_bar = ttk.Frame(self, style="App.TFrame")
        recorder_bar.pack(fill=tk.X, padx=8, pady=(12, 6))

        ttk.Label(
            recorder_bar, text="Recorder", style="App.Title.TLabel"
        ).pack(side=tk.LEFT)

        ttk.Button(
            recorder_bar,
            text="Create recorder job",
            command=self._open_create_job_dialog,
            style="App.Toolbar.AccentText.TButton",
        ).pack(side=tk.RIGHT)

        self.selection_bar = ttk.Frame(self, style="App.TFrame")
        self.selection_bar.pack(fill=tk.X, padx=8, pady=(0, 6))
        self.selected_label = ttk.Label(
            self.selection_bar, text="Selected: 0", style="App.TLabel"
        )
        self.selected_label.pack(side=tk.LEFT)
        self.stop_all_button = ttk.Button(
            self.selection_bar,
            text="Stop selected",
            command=self._stop_selected,
            style="App.Toolbar.TButton",
        )
        self.stop_all_button.pack(side=tk.RIGHT)
        self.stop_all_button.pack_forget()
        self.select_all_button = ttk.Button(
            self.selection_bar,
            text="Select all",
            command=self._select_all_jobs,
            style="App.Toolbar.TButton",
        )
        self.select_all_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.select_all_button.pack_forget()
        self.clear_all_button = ttk.Button(
            self.selection_bar,
            text="Clear",
            command=self._clear_all_jobs,
            style="App.Toolbar.TButton",
        )
        self.clear_all_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.clear_all_button.pack_forget()

        self.jobs_container = ttk.Frame(self, style="App.TFrame")
        self.jobs_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 16))
        self.jobs_canvas = tk.Canvas(self.jobs_container, highlightthickness=0)
        self.jobs_scroll = ttk.Scrollbar(
            self.jobs_container, orient="vertical", command=self.jobs_canvas.yview
        )
        self.jobs_frame = ttk.Frame(self.jobs_canvas)
        self.jobs_canvas.configure(yscrollcommand=self.jobs_scroll.set)
        self._jobs_window = self.jobs_canvas.create_window(
            (0, 0), window=self.jobs_frame, anchor="nw"
        )
        self.jobs_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.jobs_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.jobs_frame.bind(
            "<Configure>",
            lambda e: self.jobs_canvas.configure(
                scrollregion=self.jobs_canvas.bbox("all")
            ),
        )
        self.jobs_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.jobs_frame.bind("<MouseWheel>", self._on_mousewheel)
        self.jobs_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.jobs_canvas.bind("<Configure>", self._on_canvas_configure)
        self.empty_state = EmptyState(
            self,
            title="No recorder jobs",
            message="Create a recorder job to start saving footage automatically.",
            icon="\uf03d",
            action_text="Create recorder job",
            action=self._open_create_job_dialog,
        )
        self.empty_state.pack_forget()

    def _refresh_jobs(self) -> None:
        jobs = self.recorder_manager.list_jobs()
        job_names = {job.camera_name for job in jobs}

        for name, entry in list(self._job_cards.items()):
            if name not in job_names:
                frame = entry["frame"]
                frame.destroy()
                self._job_cards.pop(name, None)
                if name in self._selected_jobs:
                    self._selected_jobs.remove(name)

        if not jobs:
            self.jobs_container.pack_forget()
            self.empty_state.pack(fill=tk.BOTH, expand=True, pady=(0, 16))
        else:
            self.empty_state.pack_forget()
            self.jobs_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 16))
            for job in jobs:
                camera = self.camera_manager.get_camera(job.camera_name)
                entry = self._job_cards.get(job.camera_name)
                if entry is None:
                    entry = self._create_job_card(camera, job)
                    self._job_cards[job.camera_name] = entry
                else:
                    entry["status_var"].set(job.status)
                    entry["source_var"].set(
                        "Device" if camera.source == "device" else "RTSP"
                    )
                    entry["fps_var"].set(f"Write FPS: {job.fps:.1f}")
                    motion_var = entry.get("motion_var")
                    if isinstance(motion_var, tk.BooleanVar):
                        motion_var.set(bool(job.motion_enabled))
            self._layout_cards(jobs)

        self._update_selection_ui()
        self.after(1000, self._refresh_jobs)

    def _create_job_card(self, camera: CameraConfig, job) -> dict[str, object]:
        card = ttk.Frame(self.jobs_frame, padding=10, relief="ridge")

        header = ttk.Frame(card, style="Recorder.CardHeader.TFrame")
        header.pack(fill=tk.X)
        selected_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            header,
            variable=selected_var,
            style="Recorder.CardHeader.TCheckbutton",
            command=lambda name=camera.name, var=selected_var: self._toggle_select(
                name, var
            ),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(
            header,
            text=camera.name,
            style="Recorder.CardHeader.TLabel",
        ).pack(side=tk.LEFT)
        status_var = tk.StringVar(value=job.status)
        ttk.Label(
            header,
            textvariable=status_var,
            style="Recorder.CardHeaderStatus.TLabel",
        ).pack(side=tk.RIGHT)
        header.bind(
            "<Button-1>",
            lambda _e, name=camera.name, var=selected_var: self._toggle_header_select(
                name, var
            ),
        )
        header.bind("<Enter>", lambda _e: header.configure(cursor="hand2"))
        header.bind("<Leave>", lambda _e: header.configure(cursor=""))
        for widget in header.winfo_children():
            if isinstance(widget, ttk.Checkbutton):
                continue
            widget.bind(
                "<Button-1>",
                lambda _e, name=camera.name, var=selected_var: self._toggle_header_select(
                    name, var
                ),
            )
            widget.bind("<Enter>", lambda _e, w=widget: w.configure(cursor="hand2"))
            widget.bind("<Leave>", lambda _e, w=widget: w.configure(cursor=""))

        details = ttk.Frame(card)
        details.pack(fill=tk.X, pady=(6, 0))
        start_text = datetime.fromtimestamp(job.start_time).strftime(
            "%d-%m-%Y %H:%M:%S"
        )
        ttk.Label(
            details, text=f"Start: {start_text}", font=("Bai Jamjuree", 11)
        ).pack(side=tk.LEFT)
        source_var = tk.StringVar(
            value="Device" if camera.source == "device" else "RTSP"
        )
        ttk.Label(
            details,
            textvariable=source_var,
            font=("Bai Jamjuree", 11),
        ).pack(side=tk.LEFT, padx=(16, 0))

        fps_frame = ttk.Frame(card)
        fps_frame.pack(fill=tk.X, pady=(2, 0))
        fps_var = tk.StringVar(value=f"Write FPS: {job.fps:.1f}")
        ttk.Label(
            fps_frame,
            textvariable=fps_var,
            font=("Bai Jamjuree", 11),
        ).pack(side=tk.LEFT)
        motion_var = tk.BooleanVar(value=bool(job.motion_enabled))
        motion_toggle = ttk.Checkbutton(
            fps_frame,
            text="Motion",
            variable=motion_var,
            style="Recorder.Motion.TCheckbutton",
            command=lambda name=camera.name, var=motion_var: self._toggle_motion(
                name, var
            ),
        )
        if not self.recorder_manager.is_motion_available():
            motion_toggle.state(["disabled"])
        motion_toggle.pack(side=tk.RIGHT)
        actions = ttk.Frame(card)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            actions,
            text="Live",
            command=lambda cam=camera: open_live(
                self, cam, self.stream_manager, self.frame_store
            ),
        ).pack(side=tk.LEFT)
        ttk.Button(
            actions,
            text="Stop",
            command=lambda name=camera.name: self._stop_job(name),
        ).pack(side=tk.RIGHT)

        return {
            "frame": card,
            "status_var": status_var,
            "source_var": source_var,
            "fps_var": fps_var,
            "selected_var": selected_var,
            "motion_var": motion_var,
        }

    def _toggle_header_select(self, name: str, var: tk.BooleanVar) -> None:
        var.set(not var.get())
        self._toggle_select(name, var)

    def _layout_cards(self, jobs: list | None = None) -> None:
        if jobs is None:
            jobs = self.recorder_manager.list_jobs()
        if not jobs:
            return
        width = self.jobs_canvas.winfo_width()
        if width <= 1:
            self.after(50, lambda: self._layout_cards(jobs))
            return
        min_card = 300
        gap = 12
        cols = max(1, min(len(jobs), width // (min_card + gap)))
        if (
            self._layout_state["cols"] == cols
            and self._layout_state["count"] == len(jobs)
            and abs(self._layout_state["width"] - width) < 5
        ):
            return
        self._layout_state.update({"cols": cols, "count": len(jobs), "width": width})
        for entry in self._job_cards.values():
            entry["frame"].grid_forget()
        for col in range(cols):
            self.jobs_frame.columnconfigure(col, weight=1)
        for idx, job in enumerate(jobs):
            entry = self._job_cards.get(job.camera_name)
            if entry is None:
                continue
            row = idx // cols
            col = idx % cols
            entry["frame"].grid(row=row, column=col, padx=6, pady=6, sticky="ew")

    def _on_mousewheel(self, event: tk.Event) -> None:
        region = self.jobs_canvas.bbox("all")
        if not region:
            return
        _, _, _, region_h = region
        canvas_h = self.jobs_canvas.winfo_height()
        if region_h <= canvas_h:
            return
        if not self._is_over_jobs(event.widget):
            return
        self.jobs_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_canvas_configure(self, event: tk.Event) -> None:
        scroll_w = self.jobs_scroll.winfo_width()
        self.jobs_canvas.itemconfigure(self._jobs_window, width=max(0, event.width - scroll_w))
        self._layout_cards()

    def _is_over_jobs(self, widget: tk.Misc) -> bool:
        if widget is self.jobs_canvas or widget is self.jobs_frame:
            return True
        return str(widget).startswith(str(self.jobs_frame))

    def _open_create_job_dialog(self) -> None:
        JobDialog(self, self.camera_manager, self.recorder_manager).open()

    def _toggle_select(self, name: str, var: tk.BooleanVar) -> None:
        if var.get():
            self._selected_jobs.add(name)
        else:
            self._selected_jobs.discard(name)
        self._update_selection_ui()

    def _update_selection_ui(self) -> None:
        count = len(self._selected_jobs)
        self.selected_label.config(text=f"Selected: {count}")
        if count > 0:
            self.stop_all_button.pack(side=tk.RIGHT)
            self.clear_all_button.pack(side=tk.RIGHT, padx=(0, 8))
        else:
            self.stop_all_button.pack_forget()
            self.clear_all_button.pack_forget()
        if self._job_cards:
            self.select_all_button.pack(side=tk.RIGHT, padx=(0, 8))
        else:
            self.select_all_button.pack_forget()

    def _toggle_motion(self, name: str, var: tk.BooleanVar) -> None:
        if not self.recorder_manager.is_motion_available():
            messagebox.showinfo(
                "Motion unavailable",
                "Offline motion is disabled in settings.",
            )
            var.set(False)
            return
        self.recorder_manager.set_job_motion_enabled(name, bool(var.get()))

    def _select_all_jobs(self) -> None:
        for name, entry in self._job_cards.items():
            var = entry.get("selected_var")
            if isinstance(var, tk.BooleanVar):
                var.set(True)
            self._selected_jobs.add(name)
        self._update_selection_ui()

    def _clear_all_jobs(self) -> None:
        for name, entry in self._job_cards.items():
            var = entry.get("selected_var")
            if isinstance(var, tk.BooleanVar):
                var.set(False)
        self._selected_jobs.clear()
        self._update_selection_ui()

    def _stop_selected(self) -> None:
        if not self._selected_jobs:
            return
        if not messagebox.askyesno(
            "Stop selected", f"Stop {len(self._selected_jobs)} selected jobs?"
        ):
            return
        names = list(self._selected_jobs)
        for name in names:
            entry = self._job_cards.get(name)
            if entry and "selected_var" in entry:
                entry["selected_var"].set(False)
        self._selected_jobs.clear()
        self._update_selection_ui()

        StopJobsDialog(self, self.recorder_manager).open(
            names,
            title="Stopping selected",
            show_done_message=True,
        )

    def _stop_job(self, name: str) -> None:
        if not messagebox.askyesno("Stop job", f"Stop recording for {name}?"):
            return

        StopJobsDialog(self, self.recorder_manager).open(
            [name],
            title="Stopping",
            show_done_message=True,
        )
