import threading
import time
import tkinter as tk
from urllib.parse import quote
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk
import unicodedata

from app.core.camera_manager import CameraManager
from app.core.recorder_manager import RecorderManager


class LiveView(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        camera_manager: CameraManager,
        recorder_manager: RecorderManager,
    ) -> None:
        super().__init__(parent)
        self.camera_manager = camera_manager
        self.recorder_manager = recorder_manager
        self.selected: dict[str, tk.BooleanVar] = {}
        self.page_index = 0
        self.page_size = 9
        self.view_size = (800, 520)
        self.tile_labels: list[ttk.Label] = []
        self._latest_frames: dict[str, np.ndarray] = {}
        self._frame_lock = threading.Lock()
        self._capture_threads: dict[str, threading.Thread] = {}
        self._capture_stops: dict[str, threading.Event] = {}
        self.refresh_ms = 350
        self._build_ui()
        self._refresh_camera_list()
        self._refresh_view()

    def _build_ui(self) -> None:
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 12))

        left_panel = ttk.Frame(container, width=170)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left_panel.pack_propagate(False)

        ttk.Label(
            left_panel, text="Select Cameras", font=("Bai Jamjuree", 12, "bold")
        ).pack(anchor="w", pady=(0, 6))

        self.select_all_btn = ttk.Button(
            left_panel, text="Select all", command=self._select_all
        )
        self.select_all_btn.pack(fill=tk.X, pady=(0, 6))
        self.clear_btn = ttk.Button(left_panel, text="Clear", command=self._clear_all)
        self.clear_btn.pack(fill=tk.X, pady=(0, 10))

        self.list_canvas = tk.Canvas(left_panel, highlightthickness=0)
        self.list_scroll = ttk.Scrollbar(
            left_panel, orient="vertical", command=self.list_canvas.yview
        )
        self.list_frame = ttk.Frame(self.list_canvas)
        self.list_canvas.configure(yscrollcommand=self.list_scroll.set)
        self.list_window = self.list_canvas.create_window(
            (0, 0), window=self.list_frame, anchor="nw"
        )
        self.list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_frame.bind(
            "<Configure>",
            lambda e: self.list_canvas.configure(
                scrollregion=self.list_canvas.bbox("all")
            ),
        )
        self.list_canvas.bind(
            "<Configure>",
            lambda e: self.list_canvas.itemconfigure(self.list_window, width=e.width),
        )

        right_panel = ttk.Frame(container)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(right_panel)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        self.page_label = ttk.Label(toolbar, text="Page 1/1")
        self.page_label.pack(side=tk.LEFT)
        self.prev_btn = ttk.Button(toolbar, text="Prev", command=self._prev_page)
        self.prev_btn.pack(side=tk.RIGHT, padx=(6, 0))
        self.next_btn = ttk.Button(toolbar, text="Next", command=self._next_page)
        self.next_btn.pack(side=tk.RIGHT)

        self.view_canvas = tk.Canvas(right_panel, highlightthickness=0, bg="#111111")
        self.view_canvas.pack(fill=tk.BOTH, expand=True)
        self.view_canvas.bind("<Configure>", self._on_view_resize)
        self.bind("<Destroy>", lambda e: self._shutdown_captures())

        self.empty_label = ttk.Label(
            right_panel,
            text="Select camera(s) to view.",
            font=("Bai Jamjuree", 12),
        )

    def _refresh_camera_list(self) -> None:
        current_selected = {
            name: var.get() for name, var in self.selected.items()
        }
        for child in self.list_frame.winfo_children():
            child.destroy()
        cameras = self.camera_manager.list_cameras()
        if not cameras:
            ttk.Label(
                self.list_frame,
                text="No cameras",
                font=("Bai Jamjuree", 11),
            ).pack(anchor="w")
            self.after(1000, self._refresh_camera_list)
            return
        for cam in cameras:
            status = self._get_status(cam.name)
            if status not in {"connected", "recording"}:
                continue
            var = self.selected.get(cam.name)
            if var is None:
                var = tk.BooleanVar(value=current_selected.get(cam.name, False))
                self.selected[cam.name] = var
            else:
                var.set(current_selected.get(cam.name, var.get()))
            ttk.Checkbutton(
                self.list_frame,
                text=cam.name,
                variable=var,
                command=self._on_selection_changed,
            ).pack(anchor="w")
        self._sync_captures()
        self.after(1000, self._refresh_camera_list)

    def _on_selection_changed(self) -> None:
        self.page_index = 0
        self._sync_captures()
        self._refresh_view()

    def _select_all(self) -> None:
        for var in self.selected.values():
            var.set(True)
        self._on_selection_changed()

    def _clear_all(self) -> None:
        for var in self.selected.values():
            var.set(False)
        self._on_selection_changed()

    def _on_view_resize(self, event: tk.Event) -> None:
        self.view_size = (event.width, event.height)
        self._refresh_view()

    def _get_selected_names(self) -> list[str]:
        return [name for name, var in self.selected.items() if var.get()]

    def _sync_captures(self) -> None:
        selected = set(self._get_selected_names())
        existing = set(self._capture_threads.keys())
        for name in selected - existing:
            self._start_capture_for(name)
        for name in existing - selected:
            self._stop_capture_for(name)

    def _start_capture_for(self, name: str) -> None:
        try:
            cam = self.camera_manager.get_camera(name)
        except KeyError:
            return
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._capture_loop, args=(name, cam, stop_event), daemon=True
        )
        self._capture_stops[name] = stop_event
        self._capture_threads[name] = thread
        thread.start()

    def _stop_capture_for(self, name: str) -> None:
        stop = self._capture_stops.pop(name, None)
        if stop:
            stop.set()
        self._capture_threads.pop(name, None)
        with self._frame_lock:
            self._latest_frames.pop(name, None)

    def _shutdown_captures(self) -> None:
        for name in list(self._capture_threads.keys()):
            self._stop_capture_for(name)

    def _build_rtsp_url(self, cam) -> str:
        if cam.rtsp_url:
            return cam.rtsp_url
        user = quote(cam.user, safe="")
        password = quote(cam.password, safe="")
        auth = f"{user}:{password}@" if user or password else ""
        return f"rtsp://{auth}{cam.ip}:{cam.port}{cam.stream_path}"

    def _capture_loop(self, name: str, cam, stop_event: threading.Event) -> None:
        backoff = 0.5
        cap = None
        while not stop_event.is_set():
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                if cam.source == "device":
                    cap = cv2.VideoCapture(cam.device_index)
                else:
                    cap = cv2.VideoCapture(self._build_rtsp_url(cam))
                if not cap.isOpened():
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 5.0)
                    continue
                backoff = 0.5
            if not cap.grab():
                time.sleep(0.02)
                cap.release()
                cap = None
                continue
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                time.sleep(0.02)
                cap.release()
                cap = None
                continue
            with self._frame_lock:
                self._latest_frames[name] = frame
        if cap is not None:
            cap.release()

    def _grid_for_count(self, count: int) -> tuple[int, int]:
        if count <= 1:
            return (1, 1)
        if count == 2:
            return (2, 1)
        if count <= 4:
            return (2, 2)
        if count <= 6:
            return (3, 2)
        return (3, 3)

    def _prev_page(self) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._refresh_view()

    def _next_page(self) -> None:
        names = self._get_selected_names()
        max_page = max(0, (len(names) - 1) // self.page_size)
        if self.page_index < max_page:
            self.page_index += 1
            self._refresh_view()

    def _ensure_tiles(self, count: int) -> None:
        while len(self.tile_labels) < count:
            label = ttk.Label(self.view_canvas, background="#111111")
            self.tile_labels.append(label)
        for idx, label in enumerate(self.tile_labels):
            if idx < count:
                label.place_forget()
            else:
                label.place_forget()

    def _get_status(self, name: str) -> str:
        if name in self.recorder_manager.list_active():
            return "recording"
        try:
            runtime = self.camera_manager.get_runtime(name)
            return runtime.status
        except Exception:
            return "offline"

    def _draw_placeholder(self, width: int, height: int, label: str) -> np.ndarray:
        frame = np.full((height, width, 3), 20, dtype=np.uint8)
        label = self._ascii_label(label)
        cv2.putText(
            frame,
            label,
            (10, max(30, height // 2)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )
        return frame

    def _refresh_view(self) -> None:
        names = self._get_selected_names()
        if not names:
            for label in self.tile_labels:
                label.place_forget()
            self.page_label.config(text="Page 0/0")
            self.prev_btn.config(state="disabled")
            self.next_btn.config(state="disabled")
            return

        max_page = max(0, (len(names) - 1) // self.page_size)
        if self.page_index > max_page:
            self.page_index = max_page
        start = self.page_index * self.page_size
        page_names = names[start : start + self.page_size]

        rows, cols = self._grid_for_count(len(page_names))
        w, h = self.view_size
        tile_w = max(1, w // cols)
        tile_h = max(1, h // rows)

        self._ensure_tiles(len(page_names))
        for idx, name in enumerate(page_names):
            row = idx // cols
            col = idx % cols
            x = col * tile_w
            y = row * tile_h

            with self._frame_lock:
                frame = self._latest_frames.get(name)
            if frame is None:
                frame = self._draw_placeholder(tile_w, tile_h, name)
            else:
                frame = self._fit_to_tile(frame, tile_w, tile_h)
            cv2.rectangle(frame, (2, 2), (tile_w - 3, tile_h - 3), (0, 200, 255), 2)
            cv2.putText(
                frame,
                f"{self._ascii_label(name)} | #{idx + 1}",
                (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            photo = ImageTk.PhotoImage(img)
            label = self.tile_labels[idx]
            label.configure(image=photo)
            label.image = photo
            label.place(x=x, y=y, width=tile_w, height=tile_h)

        self.page_label.config(text=f"Page {self.page_index + 1}/{max_page + 1}")
        self.prev_btn.config(state="normal" if self.page_index > 0 else "disabled")
        self.next_btn.config(
            state="normal" if self.page_index < max_page else "disabled"
        )

        self.after(self.refresh_ms, self._refresh_view)

    def _fit_to_tile(self, frame: np.ndarray, tile_w: int, tile_h: int) -> np.ndarray:
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return self._draw_placeholder(tile_w, tile_h, "No frame")
        scale = min(tile_w / float(w), tile_h / float(h))
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        resized = cv2.resize(frame, (new_w, new_h))
        canvas = np.full((tile_h, tile_w, 3), 10, dtype=np.uint8)
        y = (tile_h - new_h) // 2
        x = (tile_w - new_w) // 2
        canvas[y : y + new_h, x : x + new_w] = resized
        return canvas

    def _ascii_label(self, text: str) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text)
        return normalized.encode("ascii", "ignore").decode("ascii")
