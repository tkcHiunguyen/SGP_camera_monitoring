from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk

from app.config.models import CameraConfig
from app.core.camera_manager import CameraManager
from app.core.recorder_manager import RecorderManager
from app.ui.job_dialog import JobDialog
from app.ui.stop_jobs_dialog import StopJobsDialog
from app.ui.live_actions import open_live


class RecorderView(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        camera_manager: CameraManager,
        recorder_manager: RecorderManager,
    ) -> None:
        super().__init__(parent)
        self.camera_manager = camera_manager
        self.recorder_manager = recorder_manager
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
        style.configure("Recorder.CardHeader.TCheckbutton", background="#dbe4f0")

        recorder_bar = ttk.Frame(self)
        recorder_bar.pack(fill=tk.X, padx=8, pady=(12, 6))

        ttk.Label(
            recorder_bar, text="Recorder", font=("Bai Jamjuree", 12, "bold")
        ).pack(side=tk.LEFT)

        ttk.Button(
            recorder_bar,
            text="Create recorder job",
            command=self._open_create_job_dialog,
        ).pack(side=tk.RIGHT)

        self.selection_bar = ttk.Frame(self)
        self.selection_bar.pack(fill=tk.X, padx=8, pady=(0, 6))
        self.selected_label = ttk.Label(
            self.selection_bar, text="Selected: 0", font=("Bai Jamjuree", 11)
        )
        self.selected_label.pack(side=tk.LEFT)
        self.stop_all_button = ttk.Button(
            self.selection_bar, text="Stop selected", command=self._stop_selected
        )
        self.stop_all_button.pack(side=tk.RIGHT)
        self.stop_all_button.pack_forget()

        self.jobs_container = ttk.Frame(self)
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
        self.empty_jobs = ttk.Label(
            self,
            text="No active recorder jobs yet.",
            font=("Bai Jamjuree", 12),
        )
        self.empty_jobs.pack_forget()

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
            self.empty_jobs.pack(pady=(0, 16))
        else:
            self.empty_jobs.pack_forget()
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
                    entry["motion_var"].set(
                        self.recorder_manager.get_motion_enabled(job.camera_name)
                    )
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
        motion_var = tk.BooleanVar(value=False)
        motion_check = ttk.Checkbutton(
            fps_frame,
            text="Motion detection",
            variable=motion_var,
            command=lambda name=camera.name, var=motion_var: self._toggle_motion(
                name, var
            ),
        )
        motion_check.pack(side=tk.LEFT, padx=(16, 0))
        motion_var.set(False)

        actions = ttk.Frame(card)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            actions,
            text="Live",
            command=lambda cam=camera: open_live(self, cam),
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
            "motion_var": motion_var,
            "selected_var": selected_var,
        }

    def _toggle_header_select(self, name: str, var: tk.BooleanVar) -> None:
        var.set(not var.get())
        self._toggle_select(name, var)

    def _toggle_motion(self, name: str, var: tk.BooleanVar) -> None:
        self.recorder_manager.set_motion_enabled(name, var.get())

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
        self.jobs_canvas.itemconfigure(self._jobs_window, width=event.width)
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
        else:
            self.stop_all_button.pack_forget()

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
