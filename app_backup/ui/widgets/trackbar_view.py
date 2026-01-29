import tkinter as tk


class TrackbarView(tk.Frame):
    def __init__(self, parent: tk.Misc, pad_left: int, pad_right: int) -> None:
        super().__init__(parent, bg="#111111")
        self._current_label = tk.Label(
            self, text="00:00", fg="#e5e7eb", bg="#111111", font=("Bai Jamjuree", 10)
        )
        self._current_label.pack(side=tk.LEFT, padx=(pad_left, 8), pady=(10, 0))
        self._canvas = tk.Canvas(self, height=36, highlightthickness=0, bg="#111111")
        self._canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._canvas.bind("<Enter>", lambda _e: self._canvas.configure(cursor="hand2"))
        self._canvas.bind("<Leave>", lambda _e: self._canvas.configure(cursor=""))
        self._duration_label = tk.Label(
            self, text="00:00", fg="#e5e7eb", bg="#111111", font=("Bai Jamjuree", 10)
        )
        self._duration_label.pack(side=tk.RIGHT, padx=(8, pad_right), pady=(10, 0))
        self._on_seek = None
        self._trim_visible = False
        self._trim_start = 0.2
        self._trim_end = 0.8
        self._last_ratio = 0.0
        self._dragging = None
        self._handle_radius = 8
        self._duration_seconds = 0.0
        self._canvas.bind("<ButtonPress-1>", self._on_click)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

    def set_seek_handler(self, handler) -> None:
        self._on_seek = handler

    def set_times(self, current: str, duration: str) -> None:
        self._current_label.configure(text=current)
        self._duration_label.configure(text=duration)

    def set_duration_seconds(self, seconds: float) -> None:
        self._duration_seconds = max(0.0, float(seconds))

    def draw_progress(self, ratio: float) -> None:
        ratio = max(0.0, min(1.0, ratio))
        self._last_ratio = ratio
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w <= 1 or h <= 1:
            return
        self._canvas.delete("all")
        bar_y = max(10, h - 10)
        self._canvas.create_line(
            6, bar_y, w - 6, bar_y, fill="#4b5563", width=3, capstyle="round"
        )
        handle_x = int(4 + (w - 8) * ratio)
        self._canvas.create_line(
            6, bar_y, handle_x, bar_y, fill="#f59e0b", width=4, capstyle="round"
        )
        if self._trim_visible:
            start_x = int(4 + (w - 8) * max(0.0, min(1.0, self._trim_start)))
            end_x = int(4 + (w - 8) * max(0.0, min(1.0, self._trim_end)))
            if start_x > end_x:
                start_x, end_x = end_x, start_x
            if self._duration_seconds > 0:
                start_time = self._fmt_time(self._trim_start * self._duration_seconds)
                end_time = self._fmt_time(self._trim_end * self._duration_seconds)
                start_text = self._canvas.create_text(
                    start_x,
                    bar_y - (self._handle_radius + 10),
                    text=start_time,
                    fill="#e2e8f0",
                    font=("Bai Jamjuree", 10, "bold"),
                    tags=("trim_label",),
                )
                end_text = self._canvas.create_text(
                    end_x,
                    bar_y - (self._handle_radius + 10),
                    text=end_time,
                    fill="#e2e8f0",
                    font=("Bai Jamjuree", 10, "bold"),
                    tags=("trim_label",),
                )
                for text_id in (start_text, end_text):
                    bbox = self._canvas.bbox(text_id)
                    if bbox is None:
                        continue
                    pad = 2
                    rect = self._canvas.create_rectangle(
                        bbox[0] - pad,
                        bbox[1] - pad,
                        bbox[2] + pad,
                        bbox[3] + pad,
                        fill="#0f172a",
                        outline="#1e293b",
                        width=1,
                    )
                    self._canvas.tag_lower(rect, text_id)
            self._canvas.create_oval(
                start_x - self._handle_radius,
                bar_y - (self._handle_radius + 1),
                start_x + self._handle_radius,
                bar_y + (self._handle_radius + 1),
                fill="#22d3ee",
                outline="#0ea5e9",
                width=1,
            )
            self._canvas.create_oval(
                end_x - self._handle_radius,
                bar_y - (self._handle_radius + 1),
                end_x + self._handle_radius,
                bar_y + (self._handle_radius + 1),
                fill="#fb7185",
                outline="#e11d48",
                width=1,
            )
        self._canvas.create_oval(
            handle_x - 5,
            bar_y - 5,
            handle_x + 5,
            bar_y + 5,
            fill="#fbbf24",
            outline="#92400e",
            width=1,
        )

    def _on_click(self, event) -> None:
        w = self._canvas.winfo_width()
        if w <= 1:
            return
        if self._trim_visible:
            hit = self._hit_test(event.x, w)
            if hit is not None:
                self._dragging = hit
                self._update_trim(event.x, w)
                return
        if self._on_seek is None:
            return
        ratio = max(0.0, min(1.0, event.x / float(w)))
        self._on_seek(ratio)

    def _on_drag(self, event) -> None:
        if not self._trim_visible or self._dragging is None:
            return
        w = self._canvas.winfo_width()
        if w <= 1:
            return
        self._update_trim(event.x, w)

    def _on_release(self, _event) -> None:
        self._dragging = None

    def set_trim_visible(self, visible: bool) -> None:
        self._trim_visible = visible
        self.draw_progress(self._last_ratio)

    def _hit_test(self, x: int, w: int) -> str | None:
        start_x = int(4 + (w - 8) * max(0.0, min(1.0, self._trim_start)))
        end_x = int(4 + (w - 8) * max(0.0, min(1.0, self._trim_end)))
        dist_start = abs(x - start_x)
        dist_end = abs(x - end_x)
        hit_radius = self._handle_radius + 6
        if dist_start <= hit_radius or dist_end <= hit_radius:
            return "start" if dist_start <= dist_end else "end"
        return None

    def _update_trim(self, x: int, w: int) -> None:
        ratio = max(0.0, min(1.0, (x - 4) / float(max(1, w - 8))))
        if self._dragging == "start":
            self._trim_start = min(ratio, self._trim_end)
        elif self._dragging == "end":
            self._trim_end = max(ratio, self._trim_start)
        self.draw_progress(self._last_ratio)

    def get_trim_range(self) -> tuple[float, float]:
        return (min(self._trim_start, self._trim_end), max(self._trim_start, self._trim_end))

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        secs = max(0, int(seconds))
        mins = secs // 60
        secs = secs % 60
        return f"{mins:02d}:{secs:02d}"
