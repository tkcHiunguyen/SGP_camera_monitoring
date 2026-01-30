import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk
import unicodedata

from app.core.camera_manager import CameraManager
from app.core.recorder_manager import RecorderManager
from app.ui.widgets.empty_state import EmptyState


class LiveView(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        camera_manager: CameraManager,
        recorder_manager: RecorderManager,
        on_fullscreen_toggle: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.camera_manager = camera_manager
        self.recorder_manager = recorder_manager
        self.selected: dict[str, tk.BooleanVar] = {}
        self.page_index = 0
        self.page_size = 9
        self._layout_mode = "Auto"
        self.view_size = (800, 520)
        self.tile_labels: list[ttk.Label] = []
        self._latest_frames: dict[str, tuple[np.ndarray, int]] = {}
        self._frame_queue: queue.Queue[tuple[str, np.ndarray, int]] = queue.Queue(
            maxsize=96
        )
        self._queue_poll_ms = 30
        self._capture_threads: dict[str, threading.Thread] = {}
        self._capture_stops: dict[str, threading.Event] = {}
        self.refresh_ms = 350
        self._preview_max_dim = 960
        self._fullscreen = False
        self._sidebar_hidden = False
        self._container: ttk.Frame | None = None
        self._left_panel: ttk.Frame | None = None
        self._right_panel: ttk.Frame | None = None
        self._toolbar: ttk.Frame | None = None
        self._layout_button: ttk.Button | None = None
        self._layout_popup: tk.Toplevel | None = None
        self._layout_previews: dict[str, ImageTk.PhotoImage] = {}
        self._sidebar_toggle_btn: ttk.Button | None = None
        self._sidebar_show_btn: ttk.Button | None = None
        self._fullscreen_exit_btn: ttk.Button | None = None
        self._fs_prev_btn: tk.Button | None = None
        self._fs_next_btn: tk.Button | None = None
        self._list_bg = "#f5f6f8"
        self._list_hover_bg = "#e7edf5"
        self._list_selected_bg = "#dbeaff"
        self._list_selected_hover_bg = "#cfe2ff"
        self._list_selected_fg = "#0b3d6e"
        self._list_fg = "#111111"
        self._pause_list_refresh = False
        self._hover_row: str | None = None
        self._camera_list_signature: tuple[str, ...] = ()
        self._tree_item_to_name: dict[str, str] = {}
        self._tree_icons: dict[str, ImageTk.PhotoImage] = {}
        self._toolbar_bg = "#f5f6f8"
        self._on_fullscreen_toggle = on_fullscreen_toggle
        self._build_ui()
        self._refresh_camera_list()
        self._load_layout_previews()
        self._update_preview_quality()
        self._render_view()
        self.after(self._queue_poll_ms, self._poll_frame_queue)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        self._container = container

        left_panel = ttk.Frame(container, width=170, style="App.TFrame")
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left_panel.pack_propagate(False)
        self._left_panel = left_panel

        sidebar_header = ttk.Frame(left_panel, style="App.TFrame")
        sidebar_header.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(sidebar_header, text="Select Cameras", style="App.Title.TLabel").pack(
            side=tk.LEFT, anchor="w"
        )

        self.select_all_btn = ttk.Button(
            left_panel,
            text="Select all",
            command=self._select_all,
            style="App.Toolbar.TButton",
        )
        self.select_all_btn.pack(fill=tk.X, pady=(0, 6))
        self.clear_btn = ttk.Button(
            left_panel,
            text="Clear",
            command=self._clear_all,
            style="App.Toolbar.TButton",
        )
        self.clear_btn.pack(fill=tk.X, pady=(0, 10))

        style = ttk.Style(self)
        theme_bg = style.lookup("App.TFrame", "background")
        if isinstance(theme_bg, str) and theme_bg.startswith("#"):
            self._list_bg = theme_bg
            self._toolbar_bg = theme_bg
        self._list_hover_bg = self._adjust_hex_color(self._list_bg, -24)
        style.configure(
            "Liveview.Treeview", font=("Bai Jamjuree", 11), rowheight=28, indent=2
        )
        self.list_tree = ttk.Treeview(
            left_panel,
            show="tree",
            selectmode="none",
            style="App.Treeview",
        )
        self.list_tree.tag_configure(
            "hover", background=self._list_hover_bg, foreground=self._list_fg
        )
        self.list_tree.tag_configure(
            "selected",
            background=self._list_selected_bg,
            foreground=self._list_selected_fg,
        )
        self.list_tree.tag_configure(
            "selected_hover",
            background=self._list_selected_hover_bg,
            foreground=self._list_selected_fg,
        )
        self.list_scroll = ttk.Scrollbar(
            left_panel, orient="vertical", command=self.list_tree.yview
        )
        self.list_tree.configure(yscrollcommand=self.list_scroll.set)
        self.list_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._load_tree_icons()
        self.list_tree.bind("<MouseWheel>", self._on_tree_mousewheel)
        self.list_tree.bind("<Button-4>", self._on_tree_mousewheel_linux)
        self.list_tree.bind("<Button-5>", self._on_tree_mousewheel_linux)
        self.list_tree.bind("<Enter>", self._pause_camera_list_refresh, add="+")
        self.list_tree.bind("<Leave>", self._resume_camera_list_refresh, add="+")
        self.list_tree.bind("<Motion>", self._on_tree_hover_move, add="+")
        self.list_tree.bind("<Leave>", self._clear_tree_hover, add="+")
        self.list_tree.bind("<Button-1>", self._on_tree_click)

        right_panel = ttk.Frame(container, style="App.TFrame")
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._right_panel = right_panel
        right_panel.bind("<Configure>", self._on_panel_resize)

        toolbar = ttk.Frame(right_panel, style="App.TFrame")
        toolbar.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        self._toolbar = toolbar
        self.page_label = ttk.Label(toolbar, text="Page 1/1", style="App.TLabel")
        self.page_label.pack(side=tk.LEFT)
        self._layout_button = ttk.Button(
            toolbar,
            text="Layout: Auto",
            style="App.Toolbar.TButton",
            command=self._open_layout_popup,
        )
        self._layout_button.pack(side=tk.LEFT, padx=(10, 0))
        style.configure(
            "Liveview.Fullscreen.TButton", font=("Font Awesome 6 Free Solid", 11)
        )
        style.configure("Liveview.Icon.TButton", font=("Font Awesome 6 Free Solid", 11))
        self.fullscreen_btn = tk.Button(
            toolbar,
            text="\uf065",
            command=self._toggle_fullscreen,
            font=("Font Awesome 6 Free Solid", 14),
            fg="#4b5563",
            bg=self._toolbar_bg,
            activeforeground="#111111",
            activebackground=self._toolbar_bg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            highlightbackground=self._toolbar_bg,
            padx=4,
            pady=2,
        )
        self.fullscreen_btn.pack(side=tk.RIGHT, padx=(6, 0))
        self.next_btn = tk.Button(
            toolbar,
            text="\uf105",
            command=self._next_page,
            font=("Font Awesome 6 Free Solid", 12),
            fg="#4b5563",
            bg=self._toolbar_bg,
            activeforeground="#111111",
            activebackground=self._toolbar_bg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=4,
            pady=2,
        )
        self.prev_btn = tk.Button(
            toolbar,
            text="\uf104",
            command=self._prev_page,
            font=("Font Awesome 6 Free Solid", 12),
            fg="#4b5563",
            bg=self._toolbar_bg,
            activeforeground="#111111",
            activebackground=self._toolbar_bg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=4,
            pady=2,
        )
        self._sidebar_toggle_btn = ttk.Button(
            sidebar_header,
            text="\uf053",
            style="Liveview.Icon.TButton",
            command=self._toggle_sidebar,
            width=2,
        )
        self._sidebar_toggle_btn.pack(side=tk.RIGHT)

        self.view_canvas = tk.Canvas(right_panel, highlightthickness=0, bg="#111111")
        self.view_canvas.bind("<Configure>", self._on_view_resize)
        self.bind("<Destroy>", lambda e: self._shutdown_captures())

        self.empty_state = EmptyState(
            right_panel,
            title="No live view yet",
            message="Select one or more cameras from the left to start monitoring.",
            icon="\uf03d",
        )
        self.empty_state.pack(fill=tk.BOTH, expand=True, pady=(6, 6))
        self.view_canvas.pack_forget()
        self._fs_prev_btn = tk.Button(
            right_panel,
            text="\uf104",
            command=self._prev_page,
            font=("Font Awesome 6 Free Solid", 14),
            fg="#e6eef7",
            bg="#111111",
            activeforeground="#ffffff",
            activebackground="#111111",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=4,
            pady=2,
        )
        self._fs_next_btn = tk.Button(
            right_panel,
            text="\uf105",
            command=self._next_page,
            font=("Font Awesome 6 Free Solid", 14),
            fg="#e6eef7",
            bg="#111111",
            activeforeground="#ffffff",
            activebackground="#111111",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=4,
            pady=2,
        )
        self._fs_prev_btn.place_forget()
        self._fs_next_btn.place_forget()
        self._sidebar_show_btn = ttk.Button(
            right_panel,
            text="\uf054",
            style="Liveview.Icon.TButton",
            command=self._toggle_sidebar,
            width=2,
        )
        self._fullscreen_exit_btn = ttk.Button(
            right_panel,
            text="\uf066",
            style="Liveview.Icon.TButton",
            command=self._toggle_fullscreen,
            width=2,
        )
        self._fullscreen_exit_btn.place_forget()

    def _toggle_fullscreen(self) -> None:
        if (
            self._container is None
            or self._left_panel is None
            or self._right_panel is None
        ):
            return
        self._fullscreen = not self._fullscreen
        if self._on_fullscreen_toggle is not None:
            self._on_fullscreen_toggle(self._fullscreen)
        if self._fullscreen:
            self._left_panel.pack_forget()
            self._right_panel.pack_forget()
            self._container.configure(padding=0)
            if self._toolbar is not None:
                self._toolbar.pack_forget()
            self.prev_btn.pack_forget()
            self.next_btn.pack_forget()
            self.fullscreen_btn.pack_forget()
            self._right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        else:
            self._right_panel.pack_forget()
            self._container.configure(padding=8)
            if not self._sidebar_hidden:
                self._left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
            if self._toolbar is not None:
                self._toolbar.pack(fill=tk.X, pady=(0, 6))
                self.fullscreen_btn.pack(side=tk.RIGHT, padx=(6, 0))
            self._right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.fullscreen_btn.config(text="\uf066" if self._fullscreen else "\uf065")
        self._sync_overlay_buttons()

    def _toggle_sidebar(self) -> None:
        if self._left_panel is None or self._right_panel is None:
            return
        if self._fullscreen:
            return
        self._sidebar_hidden = not self._sidebar_hidden
        if self._sidebar_hidden:
            self._left_panel.pack_forget()
            if self._sidebar_toggle_btn is not None:
                self._sidebar_toggle_btn.config(text="\uf054")
        else:
            self._right_panel.pack_forget()
            self._left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
            self._right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            if self._sidebar_toggle_btn is not None:
                self._sidebar_toggle_btn.config(text="\uf053")
        self._sync_overlay_buttons()

    def _on_panel_resize(self, event: tk.Event) -> None:
        self._sync_overlay_buttons()

    def _sync_overlay_buttons(self) -> None:
        if self._right_panel is None:
            return
        if self._fullscreen:
            if self._fullscreen_exit_btn is not None:
                self._fullscreen_exit_btn.place(
                    relx=1.0, rely=1.0, x=-12, y=-12, anchor="se"
                )
                self._fullscreen_exit_btn.lift()
        else:
            if self._fullscreen_exit_btn is not None:
                self._fullscreen_exit_btn.place_forget()
        if self._fs_prev_btn is not None:
            self._fs_prev_btn.place(relx=0.0, rely=0.5, x=10, anchor="w")
            self._fs_prev_btn.lift()
        if self._fs_next_btn is not None:
            self._fs_next_btn.place(relx=1.0, rely=0.5, x=-10, anchor="e")
            self._fs_next_btn.lift()
        if self._sidebar_hidden and not self._fullscreen:
            if self._sidebar_show_btn is not None:
                self._sidebar_show_btn.place(relx=0.0, rely=0.0, x=6, y=6, anchor="nw")
                self._sidebar_show_btn.lift()
        else:
            if self._sidebar_show_btn is not None:
                self._sidebar_show_btn.place_forget()

    def _on_tree_mousewheel(self, event: tk.Event) -> None:
        if self.list_tree is None:
            return
        delta = -1 if event.delta > 0 else 1
        self.list_tree.yview_scroll(delta, "units")

    def _on_tree_mousewheel_linux(self, event: tk.Event) -> None:
        if self.list_tree is None:
            return
        direction = -1 if event.num == 4 else 1
        self.list_tree.yview_scroll(direction, "units")

    def _tree_label(self, name: str, selected: bool) -> str:
        return f"  {name}"

    def _load_tree_icons(self) -> None:
        if self._tree_icons:
            return
        base = Path(__file__).resolve().parents[2] / "assets" / "icons"
        on_path = base / "eye_on.png"
        off_path = base / "eye_off.png"
        if on_path.exists():
            self._tree_icons["on"] = ImageTk.PhotoImage(Image.open(on_path))
        if off_path.exists():
            self._tree_icons["off"] = ImageTk.PhotoImage(Image.open(off_path))

    def _apply_tree_item_state(self, item_id: str, selected: bool, hover: bool) -> None:
        if selected and hover:
            tags = ("selected_hover",)
        elif selected:
            tags = ("selected",)
        elif hover:
            tags = ("hover",)
        else:
            tags = ()
        name = self._tree_item_to_name.get(item_id, "")
        icon_key = "on" if selected else "off"
        icon = self._tree_icons.get(icon_key)
        self.list_tree.item(
            item_id,
            text=self._tree_label(name, selected),
            image=icon,
            tags=tags,
        )

    def _on_tree_hover_move(self, event: tk.Event) -> None:
        item_id = self.list_tree.identify_row(event.y)
        if item_id == self._hover_row:
            return
        if self._hover_row is not None:
            prev_name = self._tree_item_to_name.get(self._hover_row, "")
            prev_var = self.selected.get(prev_name)
            prev_selected = prev_var.get() if prev_var else False
            self._apply_tree_item_state(self._hover_row, prev_selected, False)
        self._hover_row = item_id if item_id else None
        if self._hover_row is not None:
            name = self._tree_item_to_name.get(self._hover_row, "")
            var = self.selected.get(name)
            selected = var.get() if var else False
            self._apply_tree_item_state(self._hover_row, selected, True)

    def _clear_tree_hover(self, event: tk.Event) -> None:
        if self._hover_row is None:
            return
        name = self._tree_item_to_name.get(self._hover_row, "")
        var = self.selected.get(name)
        selected = var.get() if var else False
        self._apply_tree_item_state(self._hover_row, selected, False)
        self._hover_row = None

    def _on_tree_click(self, event: tk.Event) -> str:
        item_id = self.list_tree.identify_row(event.y)
        if not item_id:
            return "break"
        name = self._tree_item_to_name.get(item_id)
        if not name:
            return "break"
        var = self.selected.get(name)
        if var is None:
            return "break"
        var.set(not var.get())
        self._apply_tree_item_state(item_id, var.get(), True)
        self._on_selection_changed()
        return "break"

    def _pause_camera_list_refresh(self, event: tk.Event) -> None:
        self._pause_list_refresh = True

    def _resume_camera_list_refresh(self, event: tk.Event) -> None:
        self._pause_list_refresh = False

    def _refresh_camera_list(self) -> None:
        if self._pause_list_refresh:
            self.after(1000, self._refresh_camera_list)
            return
        current_selected = {name: var.get() for name, var in self.selected.items()}
        cameras = self.camera_manager.list_cameras()
        signature = tuple(cam.name for cam in cameras)
        if signature == self._camera_list_signature:
            self.after(5000, self._refresh_camera_list)
            return
        self._camera_list_signature = signature
        self._hover_row = None
        yview = self.list_tree.yview()
        for item in self.list_tree.get_children():
            self.list_tree.delete(item)
        self._tree_item_to_name.clear()
        if not cameras:
            self.list_tree.insert("", "end", text="No cameras")
            self.after(5000, self._refresh_camera_list)
            return
        for cam in cameras:
            var = self.selected.get(cam.name)
            if var is None:
                var = tk.BooleanVar(value=current_selected.get(cam.name, False))
                self.selected[cam.name] = var
            else:
                var.set(current_selected.get(cam.name, var.get()))
            item_id = self.list_tree.insert(
                "",
                "end",
                text=self._tree_label(cam.name, var.get()),
            )
            self._tree_item_to_name[item_id] = cam.name
            self._apply_tree_item_state(item_id, var.get(), False)
        self.list_tree.yview_moveto(yview[0])
        self._sync_captures()
        self.after(5000, self._refresh_camera_list)

    def _on_selection_changed(self) -> None:
        self.page_index = 0
        self._update_preview_quality()
        self._sync_captures()
        self._render_view()

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
        self._update_preview_quality()
        self._render_view()

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
        seq = 0
        while not stop_event.is_set():
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                if cam.source == "device":
                    cap = cv2.VideoCapture(cam.device_index)
                else:
                    cap = cv2.VideoCapture(self._build_rtsp_url(cam))
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
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
            frame = self._downscale_frame(frame)
            seq += 1
            try:
                self._frame_queue.put_nowait((name, frame, seq))
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._frame_queue.put_nowait((name, frame, seq))
                except queue.Full:
                    pass
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

    def _set_layout(self, mode: str) -> None:
        self._layout_mode = mode
        if self._layout_button is not None:
            self._layout_button.configure(text=f"Layout: {mode}")
        if mode == "1x1":
            self.page_size = 1
        elif mode == "2x1":
            self.page_size = 2
        elif mode == "2x2":
            self.page_size = 4
        elif mode == "3x3":
            self.page_size = 9
        elif mode == "6x":
            self.page_size = 6
        else:
            self.page_size = 9
        self.page_index = 0
        self._render_view()

    def _open_layout_popup(self) -> None:
        if self._layout_popup is not None and self._layout_popup.winfo_exists():
            self._layout_popup.lift()
            return
        if self._layout_button is None:
            return
        popup = tk.Toplevel(self)
        popup.title("Select layout")
        popup.transient(self.winfo_toplevel())
        popup.resizable(False, False)
        popup.configure(bg="#f8fafc")
        popup.bind("<Escape>", lambda _e: popup.destroy())
        popup.bind("<FocusOut>", lambda _e: popup.destroy())
        self._layout_popup = popup

        popup.update_idletasks()
        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        width = 520
        height = 380
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        popup.geometry(f"{width}x{height}+{x}+{y}")

        container = tk.Frame(popup, bg="#f8fafc", padx=12, pady=12)
        container.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            container,
            text="Choose layout",
            font=("Bai Jamjuree", 12, "bold"),
            fg="#0f172a",
            bg="#f8fafc",
        )
        title.pack(anchor="w", pady=(0, 8))

        grid = tk.Frame(container, bg="#f8fafc")
        grid.pack()

        layouts = [
            ("Auto", "Auto"),
            ("1x1", "1x1"),
            ("2x1", "2x1"),
            ("2x2", "2x2"),
            ("3x3", "3x3"),
            ("6x", "6x"),
        ]
        for idx, (label, mode) in enumerate(layouts):
            card = self._build_layout_card(grid, label, mode)
            row = idx // 3
            col = idx % 3
            card.grid(row=row, column=col, padx=6, pady=6)

    def _build_layout_card(self, parent: tk.Misc, label: str, mode: str) -> tk.Frame:
        card = tk.Frame(parent, bg="#ffffff", bd=1, relief="solid", padx=4, pady=4)
        preview_img = self._layout_previews.get(mode)
        preview_bg = "#0b1220"
        preview_hover = "#e5e7eb"
        preview = tk.Label(card, bg=preview_bg, image=preview_img)
        preview.pack()

        btn = tk.Button(
            card,
            text=label if mode != "6x" else "6x (1 big + 5 small)",
            font=("Bai Jamjuree", 9, "bold"),
            fg="#2563eb",
            bg="#ffffff",
            activeforeground="#1d4ed8",
            activebackground="#e2e8f0",
            relief="flat",
            padx=4,
            pady=0,
            command=lambda m=mode: self._select_layout(m),
        )
        btn.pack(pady=(4, 0))
        card.bind("<Button-1>", lambda _e, m=mode: self._select_layout(m))
        preview.bind("<Button-1>", lambda _e, m=mode: self._select_layout(m))
        card.bind("<Enter>", lambda _e: preview.configure(bg=preview_hover))
        card.bind("<Leave>", lambda _e: preview.configure(bg=preview_bg))
        preview.bind("<Enter>", lambda _e: preview.configure(bg=preview_hover))
        preview.bind("<Leave>", lambda _e: preview.configure(bg=preview_bg))
        return card

    def _select_layout(self, mode: str) -> None:
        self._set_layout(mode)
        if self._layout_popup is not None and self._layout_popup.winfo_exists():
            self._layout_popup.destroy()
        self._layout_popup = None

    def _load_layout_previews(self) -> None:
        if self._layout_previews:
            return
        base = Path(__file__).resolve().parents[2] / "assets" / "layouts"
        mapping = {
            "Auto": "layout_auto.png",
            "1x1": "layout_1x1.png",
            "2x1": "layout_2x1.png",
            "2x2": "layout_2x2.png",
            "3x3": "layout_3x3.png",
            "6x": "layout_6x.png",
        }
        for key, filename in mapping.items():
            path = base / filename
            if not path.exists():
                continue
            img = Image.open(path)
            img = img.resize((130, 74), Image.LANCZOS)
            self._layout_previews[key] = ImageTk.PhotoImage(img)

    def _layout_positions(
        self, count: int, width: int, height: int
    ) -> list[tuple[int, int, int, int]]:
        if self._layout_mode == "6x":
            w3 = max(1, width // 3)
            h3 = max(1, height // 3)
            return [
                (0, 0, w3 * 2, h3 * 2),
                (w3 * 2, 0, w3, h3),
                (w3 * 2, h3, w3, h3),
                (0, h3 * 2, w3, h3),
                (w3, h3 * 2, w3, h3),
                (w3 * 2, h3 * 2, w3, h3),
            ][:count]
        if self._layout_mode in {"1x1", "2x1", "2x2", "3x3"}:
            rows, cols = self._grid_for_count(self.page_size)
        else:
            rows, cols = self._grid_for_count(count)
        tile_w = max(1, width // cols)
        tile_h = max(1, height // rows)
        positions = []
        for idx in range(count):
            row = idx // cols
            col = idx % cols
            positions.append((col * tile_w, row * tile_h, tile_w, tile_h))
        return positions

    def _update_preview_quality(self) -> None:
        count = len(self._get_selected_names())
        if count <= 1:
            self._preview_max_dim = 1280
        elif count <= 4:
            self._preview_max_dim = 960
        elif count <= 9:
            self._preview_max_dim = 640
        else:
            self._preview_max_dim = 480

    def _downscale_frame(self, frame: np.ndarray) -> np.ndarray:
        max_dim = self._preview_max_dim
        h, w = frame.shape[:2]
        if max(h, w) <= max_dim:
            return frame
        scale = max_dim / float(max(h, w))
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def _prev_page(self) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._render_view()

    def _next_page(self) -> None:
        names = self._get_selected_names()
        max_page = max(0, (len(names) - 1) // self.page_size)
        if self.page_index < max_page:
            self.page_index += 1
            self._render_view()

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

    def _poll_frame_queue(self) -> None:
        updated = False
        try:
            while True:
                name, frame, seq = self._frame_queue.get_nowait()
                self._latest_frames[name] = (frame, seq)
                updated = True
        except queue.Empty:
            pass
        if updated:
            self._render_view()
        self.after(self._queue_poll_ms, self._poll_frame_queue)

    def _render_view(self) -> None:
        names = self._get_selected_names()
        if not names:
            for label in self.tile_labels:
                label.place_forget()
            self.page_label.config(text="Page 0/0")
            self.prev_btn.config(state="disabled")
            self.next_btn.config(state="disabled")
            if self.view_canvas.winfo_ismapped():
                self.view_canvas.pack_forget()
            if not self.empty_state.winfo_ismapped():
                self.empty_state.pack(fill=tk.BOTH, expand=True, pady=(6, 6))
            return
        if self.empty_state.winfo_ismapped():
            self.empty_state.pack_forget()
        if not self.view_canvas.winfo_ismapped():
            self.view_canvas.pack(fill=tk.BOTH, expand=True)

        max_page = max(0, (len(names) - 1) // self.page_size)
        if self.page_index > max_page:
            self.page_index = max_page
        start = self.page_index * self.page_size
        page_names = names[start : start + self.page_size]

        w, h = self.view_size
        positions = self._layout_positions(len(page_names), w, h)

        self._ensure_tiles(len(page_names))
        for idx, name in enumerate(page_names):
            x, y, tile_w, tile_h = positions[idx]

            frame_entry = self._latest_frames.get(name)
            if frame_entry is None:
                frame = None
                frame_id = -1
            else:
                frame, frame_id = frame_entry
            label = self.tile_labels[idx]
            if (
                getattr(label, "camera_name", None) == name
                and getattr(label, "_last_frame_id", None) == frame_id
                and getattr(label, "_last_size", None) == (tile_w, tile_h)
                and getattr(label, "image", None) is not None
            ):
                label.place(x=x, y=y, width=tile_w, height=tile_h)
                continue
            if frame is None:
                frame = self._draw_placeholder(tile_w, tile_h, name)
            else:
                frame = self._fit_to_tile(frame, tile_w, tile_h)
            if not self._fullscreen:
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
            label.configure(image=photo)
            label.image = photo
            label.camera_name = name
            label._last_frame_id = frame_id
            label._last_size = (tile_w, tile_h)
            label.place(x=x, y=y, width=tile_w, height=tile_h)

        self.page_label.config(text=f"Page {self.page_index + 1}/{max_page + 1}")
        self.prev_btn.config(state="normal" if self.page_index > 0 else "disabled")
        self.next_btn.config(
            state="normal" if self.page_index < max_page else "disabled"
        )
        if self._fs_prev_btn is not None:
            self._fs_prev_btn.config(
                state="normal" if self.page_index > 0 else "disabled"
            )
        if self._fs_next_btn is not None:
            self._fs_next_btn.config(
                state="normal" if self.page_index < max_page else "disabled"
            )

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

    def _adjust_hex_color(self, color: str, delta: int) -> str:
        if not color or not color.startswith("#"):
            return "#e0e0e0"
        if len(color) == 4:
            color = "#" + "".join(ch * 2 for ch in color[1:])
        if len(color) != 7:
            return "#e0e0e0"
        try:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
        except ValueError:
            return "#e0e0e0"
        r = max(0, min(255, r + delta))
        g = max(0, min(255, g + delta))
        b = max(0, min(255, b + delta))
        return f"#{r:02x}{g:02x}{b:02x}"
