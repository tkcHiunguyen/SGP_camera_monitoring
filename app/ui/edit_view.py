import tkinter as tk
from tkinter import ttk
from pathlib import Path
from tkinter import filedialog, messagebox

import os
import threading
import subprocess
import cv2
import numpy as np
from PIL import Image, ImageTk
import time

from app.ui.edit_components import EditToolbar, PlaybackControls
from app.ui.widgets.trackbar_view import TrackbarView
from app.utils.paths import get_base_dir

try:
    import mpv
except Exception:
    mpv = None


class EditView(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._workspace: ttk.Frame | None = None
        self._toolbar: EditToolbar | None = None
        self._trim_enabled = False
        self._crop_enabled = False
        self._video_label: ttk.Label | None = None
        self._video_panel: tk.Frame | None = None
        self._video_path: Path | None = None
        self._video_cap = None
        self._video_playing = False
        self._video_fps = 25.0
        self._play_speed = 1.0
        self._speed_levels = [0.25, 0.5, 1, 2, 4, 8, 16, 32, 64]
        self._speed_index = 2
        self._speed_msg_until = 0.0
        self._speed_msg = ""
        self._total_frames = 0
        self._duration = 0.0
        self._trackbar: TrackbarView | None = None
        self._progress_bar = None
        self._is_seeking = False
        self._play_start_ts = 0.0
        self._play_start_frame = 0
        self._mpv_player = None
        self._mpv_duration = 0.0
        self._loop_enabled = False
        self._play_btn: tk.Button | None = None
        self._loop_btn: tk.Button | None = None
        self._stop_btn: tk.Button | None = None
        self._fullscreen = False
        self._display_box: tuple[int, int, int, int] | None = None
        self._crop_dragging = False
        self._crop_start: tuple[int, int] | None = None
        self._crop_rect: tuple[int, int, int, int] | None = None
        self._last_raw_frame: np.ndarray | None = None
        self._last_edit_params: dict | None = None
        self._processing_edit = False
        self._waiting_dialog: tk.Toplevel | None = None
        self._crop_cursor = str(
            get_base_dir() / "assets" / "icons" / "Blue Pencil 1 Normal.cur"
        )
        self._fullscreen_window: tk.Toplevel | None = None
        self._fullscreen_panel: tk.Frame | None = None
        self._fullscreen_label: ttk.Label | None = None
        self._fullscreen_exit_btn: tk.Button | None = None
        self._controls: PlaybackControls | None = None
        self._fs_controls: PlaybackControls | None = None
        self._fs_play_btn: tk.Button | None = None
        self._fs_loop_btn: tk.Button | None = None
        self._fs_trackbar: TrackbarView | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.configure(
            "Edit.Open.TButton",
            font=("Bai Jamjuree", 10, "bold"),
            padding=(0, 0),
        )
        style.configure(
            "Edit.Open.Disabled.TButton",
            font=("Bai Jamjuree", 10, "bold"),
            padding=(0, 0),
            foreground="#94a3b8",
            background="#1f2937",
        )
        style.configure(
            "Edit.Toggle.On.TButton",
            font=("Bai Jamjuree", 10, "bold"),
            padding=(0, 0),
            foreground="#22c55e",
            background="#f8fafc",
        )
        style.map(
            "Edit.Toggle.On.TButton",
            background=[("active", "#e2e8f0")],
            foreground=[("active", "#16a34a")],
        )
        self._tool_font = ("Font Awesome 6 Free Solid", 12)
        self._tool_bg = "#f8fafc"
        self._tool_hover = "#dbeafe"
        self._tool_border = "#60a5fa"
        self._tool_fg = "#111827"
        self._loop_btn = None
        style.map(
            "Edit.Open.TButton",
            background=[("active", "#e2e8f0")],
            foreground=[("active", "#111827")],
        )

        body = tk.Frame(self, bg="#111111")
        body.pack(fill=tk.BOTH, expand=True, padx=0, pady=(0, 10))

        workspace = tk.Frame(body, bg="#111111")
        workspace.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        toolbar = EditToolbar(
            workspace,
            on_open=self._open_file,
            on_trim=self._toggle_trim,
            on_crop=self._toggle_crop,
            on_save=self._on_save_edit,
        )
        toolbar.pack(side=tk.LEFT, fill=tk.Y)
        self._toolbar = toolbar

        video_area = tk.Frame(workspace, bg="#111111")
        video_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._workspace = video_area

        self._video_panel = tk.Frame(video_area, bg="#111111")
        self._video_panel.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)

        video_label = ttk.Label(video_area, background="#111111")
        video_label.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
        video_label.bind("<ButtonPress-1>", self._on_crop_press)
        video_label.bind("<B1-Motion>", self._on_crop_drag)
        video_label.bind("<ButtonRelease-1>", self._on_crop_release)
        video_label.bind("<Button-3>", self._on_crop_clear)
        self._video_label = video_label


        self._build_progress_row(body, fullscreen=False)

        controls_wrap = tk.Frame(body, bg="#111111")
        controls_wrap.pack(fill=tk.X, pady=(4, 0))
        controls = PlaybackControls(
            controls_wrap,
            on_play=self._toggle_play_pause,
            on_stop=self._stop,
            on_speed_down=self._speed_decrease,
            on_speed_up=self._speed_increase,
            on_loop=self._toggle_loop,
            on_fullscreen=self._toggle_fullscreen,
            font=self._tool_font,
            bg="#111111",
            tool_bg=self._tool_bg,
            tool_hover=self._tool_hover,
            tool_fg=self._tool_fg,
        )
        controls.pack(anchor="center")
        self._controls = controls
        self._play_btn = controls.play_button
        self._stop_btn = controls.stop_button
        self._loop_btn = controls.loop_button

    def _open_file(self) -> None:
        base_dir = get_base_dir() / "Files"
        path = filedialog.askopenfilename(
            title="Open File",
            initialdir=str(Path(base_dir)),
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mkv *.ts *.mov"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        if self._toolbar is not None:
            self._toolbar.set_trim_state(enabled=True, on=False)
            self._toolbar.set_crop_state(enabled=True, on=False)
        self._trim_enabled = False
        self._crop_enabled = False
        self._crop_rect = None
        self._apply_crop_cursor()
        self._update_save_button_visibility()
        if self._trackbar is not None:
            self._trackbar.set_trim_visible(False)
        if self._fs_trackbar is not None:
            self._fs_trackbar.set_trim_visible(False)
        if mpv is not None:
            if self._load_video_mpv(Path(path)):
                return
        self._load_video(Path(path))

    def _load_video(self, path: Path) -> None:
        if self._mpv_player is not None:
            try:
                self._mpv_player.pause = True
            except Exception:
                pass
        if self._video_cap is not None:
            try:
                self._video_cap.release()
            except Exception:
                pass
        self._video_path = path
        self._video_cap = cv2.VideoCapture(str(path))
        if not self._video_cap.isOpened():
            messagebox.showerror(
                "Open video failed",
                "Cannot open this file. It may be corrupted or missing moov atom.",
            )
            return
        self._total_frames = int(self._video_cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = self._video_cap.get(cv2.CAP_PROP_FPS) or 0.0
        if fps < 20.0 or fps > 120.0:
            fps = 30.0
        self._video_fps = fps
        self._duration = self._total_frames / fps if self._total_frames > 0 else 0.0
        self._set_time_labels(self._fmt_time(0), self._fmt_time(self._duration), self._duration)
        self._video_playing = True
        self._set_speed_index(self._speed_index)
        self._set_play_icon()
        self._play_start_ts = time.time()
        self._play_start_frame = 0
        self._play_video()


    def _load_video_mpv(self, path: Path) -> bool:
        if self._video_panel is None:
            return False
        try:
            self.update_idletasks()
            wid = self._video_panel.winfo_id()
            self._create_mpv_player(wid, path, 0.0, False)
            if self._video_label is not None:
                self._video_label.lower()
            self._schedule_progress_update()
            return True
        except Exception as exc:
            messagebox.showerror("Open video failed", f"mpv error: {exc}")
            return False

    def _play_video(self) -> None:
        if not self._video_playing or self._video_cap is None:
            return
        if self._play_start_ts == 0.0:
            self._play_start_ts = time.time()
            self._play_start_frame = int(
                self._video_cap.get(cv2.CAP_PROP_POS_FRAMES) or 0
            )
        elapsed = time.time() - self._play_start_ts
        target_frame = int(
            self._play_start_frame + elapsed * self._video_fps * self._play_speed
        )
        if target_frame < 0:
            target_frame = 0
        self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ok, frame = self._video_cap.read()
        if not ok or frame is None:
            if self._loop_enabled:
                self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._play_start_ts = time.time()
                self._play_start_frame = 0
                ok, frame = self._video_cap.read()
                if not ok or frame is None:
                    return
            else:
                self._video_playing = False
                self._set_play_icon()
                self._show_black_frame()
                return
        self._update_progress()
        self._last_raw_frame = frame
        self._render_frame(frame)
        self.after(15, self._play_video)

    def _toggle_play_pause(self) -> None:
        if self._mpv_player is not None:
            paused = bool(self._mpv_player.pause)
            if paused:
                try:
                    dur = float(self._mpv_player.duration or 0.0)
                    pos = float(self._mpv_player.time_pos or 0.0)
                except Exception:
                    dur = 0.0
                    pos = 0.0
                if dur > 0 and pos >= max(0.0, dur - 0.1):
                    try:
                        self._mpv_player.seek(0, reference="absolute")
                    except Exception:
                        pass
            self._mpv_player.pause = not paused
            self._video_playing = paused
            self._set_play_icon()
            return
        if self._video_cap is None:
            return
        if self._video_playing:
            self._video_playing = False
        else:
            if self._total_frames > 0:
                pos = int(self._video_cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
                if pos >= self._total_frames - 1:
                    self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._video_playing = True
            self._play_start_ts = time.time()
            self._play_start_frame = int(
                self._video_cap.get(cv2.CAP_PROP_POS_FRAMES) or 0
            )
            self._play_video()
        self._set_play_icon()

    def _set_play_icon(self) -> None:
        icon = "\uf04b" if not self._video_playing else "\uf04c"
        if self._play_btn is not None:
            self._play_btn.configure(text=icon)
        if self._fs_play_btn is not None:
            self._fs_play_btn.configure(text=icon)

    def _toggle_trim(self) -> None:
        if self._toolbar is None or not self._toolbar.is_trim_enabled():
            return
        self._trim_enabled = not self._trim_enabled
        self._toolbar.set_trim_state(enabled=True, on=self._trim_enabled)
        if self._duration > 0:
            if self._trackbar is not None:
                self._trackbar.set_duration_seconds(self._duration)
            if self._fs_trackbar is not None:
                self._fs_trackbar.set_duration_seconds(self._duration)
        if self._trackbar is not None:
            self._trackbar.set_trim_visible(self._trim_enabled)
        if self._fs_trackbar is not None:
            self._fs_trackbar.set_trim_visible(self._trim_enabled)
        self._update_save_button_visibility()

    def _toggle_crop(self) -> None:
        if self._toolbar is None or not self._toolbar.is_crop_enabled():
            return
        self._crop_enabled = not self._crop_enabled
        self._toolbar.set_crop_state(enabled=True, on=self._crop_enabled)
        if not self._crop_enabled:
            self._crop_rect = None
        self._apply_crop_cursor()
        self._redraw_last_frame()
        self._update_save_button_visibility()

    def _update_save_button_visibility(self) -> None:
        if self._toolbar is None:
            return
        should_show = self._trim_enabled or self._crop_enabled
        self._toolbar.show_save(should_show)

    def _on_save_edit(self) -> None:
        if self._processing_edit:
            return
        params = self._collect_edit_params()
        self._last_edit_params = params
        self._processing_edit = True
        self._show_waiting_dialog()
        threading.Thread(
            target=self._process_edit_job,
            args=(params,),
            daemon=True,
        ).start()

    def _collect_edit_params(self) -> dict:
        trim = None
        crop = None
        if self._trim_enabled and self._trackbar is not None:
            start_ratio, end_ratio = self._trackbar.get_trim_range()
            if self._duration > 0:
                trim = {
                    "start_sec": round(start_ratio * self._duration, 3),
                    "end_sec": round(end_ratio * self._duration, 3),
                }
            else:
                trim = {"start_ratio": start_ratio, "end_ratio": end_ratio}
        if self._crop_enabled and self._crop_rect and self._display_box and self._last_raw_frame is not None:
            x0, y0, w, h = self._display_box
            left = max(x0, min(x0 + w, min(self._crop_rect[0], self._crop_rect[2])))
            right = max(x0, min(x0 + w, max(self._crop_rect[0], self._crop_rect[2])))
            top = max(y0, min(y0 + h, min(self._crop_rect[1], self._crop_rect[3])))
            bottom = max(y0, min(y0 + h, max(self._crop_rect[1], self._crop_rect[3])))
            if right > left and bottom > top:
                fw = int(self._last_raw_frame.shape[1])
                fh = int(self._last_raw_frame.shape[0])
                rx1 = int(((left - x0) / max(1, w)) * fw)
                rx2 = int(((right - x0) / max(1, w)) * fw)
                ry1 = int(((top - y0) / max(1, h)) * fh)
                ry2 = int(((bottom - y0) / max(1, h)) * fh)
                crop = {
                    "x": max(0, rx1),
                    "y": max(0, ry1),
                    "w": max(0, rx2 - rx1),
                    "h": max(0, ry2 - ry1),
                }
        return {"trim": trim, "crop": crop}

    def _process_edit_job(self, params: dict) -> None:
        output_dir = None
        error = None
        try:
            if self._video_path is not None:
                output_dir = (
                    get_base_dir()
                    / "Files"
                    / "Exports"
                    / self._video_path.stem
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                out_file = output_dir / f"{self._video_path.stem}_edited.mp4"
                self._run_ffmpeg_edit(self._video_path, out_file, params)
        except Exception as exc:
            error = str(exc)
        finally:
            self.after(0, lambda: self._on_edit_job_done(output_dir, error))

    def _on_edit_job_done(self, output_dir: Path | None, error: str | None) -> None:
        self._processing_edit = False
        self._hide_waiting_dialog()
        if error:
            messagebox.showerror("Save failed", error)
            return
        self._show_saved_dialog(output_dir)

    def _run_ffmpeg_edit(self, src: Path, dst: Path, params: dict) -> None:
        trim = params.get("trim")
        crop = params.get("crop")
        cmd = ["ffmpeg", "-y"]
        if trim and "start_sec" in trim:
            cmd += ["-ss", str(trim["start_sec"])]
        cmd += ["-i", str(src)]
        if trim and "end_sec" in trim:
            cmd += ["-to", str(trim["end_sec"])]

        if crop:
            crop_filter = f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}"
            cmd += [
                "-vf",
                crop_filter,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "copy",
            ]
        else:
            cmd += ["-c", "copy"]

        cmd.append(str(dst))
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            raise RuntimeError("FFmpeg not found. Please install FFmpeg and add to PATH.")

    def _show_waiting_dialog(self) -> None:
        if self._waiting_dialog is not None:
            return
        dlg = tk.Toplevel(self)
        dlg.title("Waiting")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.configure(bg="#0f172a")
        dlg.resizable(False, False)
        label = tk.Label(
            dlg,
            text="Waiting...",
            bg="#0f172a",
            fg="#e2e8f0",
            font=("Bai Jamjuree", 12, "bold"),
            padx=24,
            pady=16,
        )
        label.pack()
        self._waiting_dialog = dlg
        self._center_dialog(dlg)

    def _hide_waiting_dialog(self) -> None:
        if self._waiting_dialog is None:
            return
        try:
            self._waiting_dialog.grab_release()
        except Exception:
            pass
        self._waiting_dialog.destroy()
        self._waiting_dialog = None

    def _show_saved_dialog(self, output_dir: Path | None) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Saved")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.configure(bg="#0f172a")
        dlg.resizable(False, False)
        path_text = str(output_dir) if output_dir is not None else "Unknown"
        label = tk.Label(
            dlg,
            text=f"SAVED\nTO: {path_text}",
            bg="#0f172a",
            fg="#e2e8f0",
            font=("Bai Jamjuree", 11, "bold"),
            padx=24,
            pady=16,
            justify="center",
        )
        label.pack()
        actions = tk.Frame(dlg, bg="#0f172a")
        actions.pack(pady=(0, 12))

        def on_open_location() -> None:
            if output_dir is None:
                return
            try:
                os.startfile(str(output_dir))
            except Exception:
                messagebox.showerror("Open location", "Cannot open folder.")

        tk.Button(
            actions,
            text="Open location",
            command=on_open_location,
            font=("Bai Jamjuree", 10, "bold"),
            relief="flat",
            bg="#e2e8f0",
            fg="#111827",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=6)
        tk.Button(
            actions,
            text="Close",
            command=dlg.destroy,
            font=("Bai Jamjuree", 10, "bold"),
            relief="flat",
            bg="#1f2937",
            fg="#e2e8f0",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=6)
        self._center_dialog(dlg)

    def _center_dialog(self, dlg: tk.Toplevel) -> None:
        dlg.update_idletasks()
        w = dlg.winfo_width()
        h = dlg.winfo_height()
        root = self.winfo_toplevel()
        x = root.winfo_rootx() + (root.winfo_width() - w) // 2
        y = root.winfo_rooty() + (root.winfo_height() - h) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _apply_crop_cursor(self) -> None:
        if self._video_label is None:
            return
        if self._crop_enabled:
            cursor_path = self._crop_cursor.replace("\\", "/")
            cursor_spec = f"@{{{cursor_path}}}"
            try:
                self._video_label.configure(cursor=cursor_spec)
            except tk.TclError:
                self._video_label.configure(cursor="crosshair")
        else:
            self._video_label.configure(cursor="")

    def _stop(self) -> None:
        if self._mpv_player is not None:
            self._mpv_player.pause = True
            self._mpv_player.seek(0, reference="absolute")
            self._video_playing = False
            self._set_play_icon()
            self._update_progress(force_reset=True)
            return
        if self._video_cap is not None:
            self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self._video_playing = False
        self._play_start_ts = 0.0
        self._play_start_frame = 0
        self._set_play_icon()
        self._show_black_frame()
        self._update_progress(force_reset=True)

    def _toggle_loop(self) -> None:
        self._loop_enabled = not self._loop_enabled
        self._sync_loop_buttons()
        if self._mpv_player is not None:
            self._mpv_player.loop_file = "inf" if self._loop_enabled else "no"

    def _sync_loop_buttons(self) -> None:
        if self._controls is not None:
            self._controls.set_loop_enabled(self._loop_enabled)
        if self._fs_controls is not None:
            self._fs_controls.set_loop_enabled(self._loop_enabled)

    def _build_progress_row(self, parent: tk.Misc, fullscreen: bool) -> None:
        pad_left = 10 if fullscreen else 6
        pad_right = 10 if fullscreen else 6
        trackbar = TrackbarView(parent, pad_left=pad_left, pad_right=pad_right)
        trackbar.pack(side=tk.BOTTOM if fullscreen else tk.TOP, fill=tk.X, pady=(10, 6))
        trackbar.set_seek_handler(self._on_seek_ratio)
        trackbar.set_trim_visible(self._trim_enabled)
        if fullscreen:
            self._fs_trackbar = trackbar
        else:
            self._trackbar = trackbar

    def _show_black_frame(self) -> None:
        target_label, w, h = self._get_render_target()
        if target_label is None or w <= 0 or h <= 0:
            return
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        img = Image.fromarray(frame)
        photo = ImageTk.PhotoImage(img)
        target_label.configure(image=photo)
        target_label.image = photo

    def _render_frame(self, frame: np.ndarray) -> None:
        target_label, w, h = self._get_render_target()
        if target_label is None or w <= 0 or h <= 0:
            return
        fh, fw = frame.shape[:2]
        scale = min(w / float(fw), h / float(fh))
        new_w = max(1, int(fw * scale))
        new_h = max(1, int(fh * scale))
        if new_w != fw or new_h != fh:
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        y = (h - new_h) // 2
        x = (w - new_w) // 2
        canvas[y : y + new_h, x : x + new_w] = frame
        self._display_box = (x, y, new_w, new_h)
        self._apply_crop_overlay(canvas)
        cv2.putText(
            canvas,
            self._speed_msg,
            (16, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 200, 255),
            2,
            cv2.LINE_AA,
        )
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        photo = ImageTk.PhotoImage(img)
        target_label.configure(image=photo)
        target_label.image = photo

    def _apply_crop_overlay(self, frame: np.ndarray) -> None:
        if not self._crop_enabled or self._crop_rect is None or self._display_box is None:
            return
        x0, y0, w, h = self._display_box
        x1, y1, x2, y2 = self._crop_rect
        x1 = max(x0, min(x0 + w, x1))
        x2 = max(x0, min(x0 + w, x2))
        y1 = max(y0, min(y0 + h, y1))
        y2 = max(y0, min(y0 + h, y2))
        if abs(x2 - x1) < 2 or abs(y2 - y1) < 2:
            return
        left = min(x1, x2)
        right = max(x1, x2)
        top = min(y1, y2)
        bottom = max(y1, y2)
        dark = (frame * 0.35).astype(np.uint8)
        dark[top:bottom, left:right] = frame[top:bottom, left:right]
        frame[:, :] = dark
        cv2.rectangle(frame, (left, top), (right, bottom), (34, 197, 94), 2)

    def _set_speed_index(self, idx: int) -> None:
        idx = max(0, min(len(self._speed_levels) - 1, idx))
        self._speed_index = idx
        self._play_speed = float(self._speed_levels[idx])
        if self._play_speed.is_integer():
            self._speed_msg = f"{int(self._play_speed)}x"
        else:
            self._speed_msg = f"{self._play_speed}x"
        self._speed_msg_until = 0.0
        if self._mpv_player is not None:
            try:
                self._mpv_player.speed = self._play_speed
            except Exception:
                pass
        elif self._video_cap is not None and self._video_playing:
            self._play_start_ts = time.time()
            self._play_start_frame = int(
                self._video_cap.get(cv2.CAP_PROP_POS_FRAMES) or 0
            )

    def _on_crop_press(self, event: tk.Event) -> None:
        if not self._crop_enabled or self._display_box is None:
            return
        x, y = self._clamp_to_display(event.x, event.y)
        self._crop_dragging = True
        self._crop_start = (x, y)
        self._crop_rect = (x, y, x, y)
        self._redraw_last_frame()

    def _on_crop_drag(self, event: tk.Event) -> None:
        if not self._crop_enabled or not self._crop_dragging or self._display_box is None:
            return
        x, y = self._clamp_to_display(event.x, event.y)
        if self._crop_start is None:
            self._crop_start = (x, y)
        sx, sy = self._crop_start
        self._crop_rect = (sx, sy, x, y)
        self._redraw_last_frame()

    def _on_crop_release(self, _event: tk.Event) -> None:
        self._crop_dragging = False

    def _on_crop_clear(self, _event: tk.Event) -> None:
        if not self._crop_enabled:
            return
        self._crop_rect = None
        self._redraw_last_frame()

    def _clamp_to_display(self, x: int, y: int) -> tuple[int, int]:
        if self._display_box is None:
            return x, y
        x0, y0, w, h = self._display_box
        x = max(x0, min(x0 + w, x))
        y = max(y0, min(y0 + h, y))
        return x, y

    def _redraw_last_frame(self) -> None:
        if self._last_raw_frame is None:
            return
        self._render_frame(self._last_raw_frame.copy())

    def _speed_increase(self) -> None:
        self._set_speed_index(self._speed_index + 1)

    def _speed_decrease(self) -> None:
        self._set_speed_index(self._speed_index - 1)

    def _toggle_fullscreen(self) -> None:
        if self._fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self) -> None:
        if self._fullscreen:
            return
        window = tk.Toplevel(self)
        window.configure(bg="#111111")
        window.attributes("-fullscreen", True)
        window.bind("<Escape>", lambda _e: self._exit_fullscreen())
        window.protocol("WM_DELETE_WINDOW", self._exit_fullscreen)
        panel = tk.Frame(window, bg="#111111")
        panel.pack(fill=tk.BOTH, expand=True)
        label = ttk.Label(panel, background="#111111")
        label.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
        self._build_progress_row(panel, fullscreen=True)
        controls_wrap = tk.Frame(panel, bg="#111111")
        controls_wrap.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 16))
        controls = PlaybackControls(
            controls_wrap,
            on_play=self._toggle_play_pause,
            on_stop=self._stop,
            on_speed_down=self._speed_decrease,
            on_speed_up=self._speed_increase,
            on_loop=self._toggle_loop,
            font=self._tool_font,
            bg="#111111",
            tool_bg=self._tool_bg,
            tool_hover=self._tool_hover,
            tool_fg=self._tool_fg,
            show_fullscreen=False,
        )
        controls.pack(anchor="center")
        exit_btn = tk.Button(
            panel,
            text="\uf066",
            command=self._exit_fullscreen,
            font=("Font Awesome 6 Free Solid", 16),
            fg="#e5e7eb",
            bg="#111111",
            activeforeground="#ffffff",
            activebackground="#111111",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=4,
            pady=2,
        )
        exit_btn.place(relx=1.0, rely=1.0, x=-16, y=-16, anchor="se")
        self._fullscreen_window = window
        self._fullscreen_panel = panel
        self._fullscreen_label = label
        self._fullscreen_exit_btn = exit_btn
        self._fs_controls = controls
        self._fs_play_btn = controls.play_button
        self._fs_loop_btn = controls.loop_button
        self._fullscreen = True
        self._set_play_icon()
        self._sync_loop_buttons()
        if self._mpv_player is not None and self._video_path is not None:
            try:
                pos = float(self._mpv_player.time_pos or 0.0)
                paused = bool(self._mpv_player.pause)
            except Exception:
                pos = 0.0
                paused = False
            try:
                self._mpv_player.terminate()
            except Exception:
                pass
            self._mpv_player = None
            self._create_mpv_player(panel.winfo_id(), self._video_path, pos, paused)
            self._schedule_progress_update()

    def _exit_fullscreen(self) -> None:
        if not self._fullscreen:
            return
        if (
            self._mpv_player is not None
            and self._video_panel is not None
            and self._video_path is not None
        ):
            try:
                pos = float(self._mpv_player.time_pos or 0.0)
                paused = bool(self._mpv_player.pause)
            except Exception:
                pos = 0.0
                paused = False
            try:
                self._mpv_player.terminate()
            except Exception:
                pass
            self._mpv_player = None
            self._create_mpv_player(
                self._video_panel.winfo_id(), self._video_path, pos, paused
            )
            self._schedule_progress_update()
        if self._fullscreen_window is not None:
            self._fullscreen_window.destroy()
        self._fullscreen_window = None
        self._fullscreen_panel = None
        self._fullscreen_label = None
        self._fullscreen_exit_btn = None
        self._fs_controls = None
        self._fs_play_btn = None
        self._fs_loop_btn = None
        self._fs_trackbar = None
        self._fullscreen = False

    def _schedule_progress_update(self) -> None:
        if self._mpv_player is None:
            return
        self._update_progress()
        self.after(800, self._schedule_progress_update)

    def _on_seek_ratio(self, ratio: float) -> None:
        was_playing = self._video_playing
        self._seek_to_ratio(ratio, resume=was_playing)
        self._draw_progress(ratio)

    def _update_progress(self, force_reset: bool = False) -> None:
        if self._mpv_player is not None:
            if force_reset:
                self._set_time_labels("00:00", "00:00", 0.0)
                self._draw_progress(0.0)
                return
            if self._is_seeking:
                return
            try:
                dur = float(self._mpv_player.duration or 0.0)
                pos = float(self._mpv_player.time_pos or 0.0)
            except Exception:
                return
            if dur > 0:
                self._draw_progress(pos / dur)
                self._set_time_labels(self._fmt_time(pos), self._fmt_time(dur), dur)
            return
        if self._video_cap is None or self._total_frames <= 0:
            self._set_time_labels("00:00", "00:00", 0.0)
            self._draw_progress(0.0)
            return
        if force_reset:
            self._set_time_labels("00:00", "00:00", 0.0)
            self._draw_progress(0.0)
            return
        frame_idx = int(self._video_cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
        progress = (frame_idx / max(1, self._total_frames)) * 100.0
        self._draw_progress(progress / 100.0)
        self._set_time_labels(
            self._fmt_time(frame_idx / max(1.0, self._video_fps)),
            self._fmt_time(self._duration),
            self._duration,
        )

    def _create_mpv_player(
        self, wid: int, path: Path, pos: float, paused: bool
    ) -> None:
        if mpv is None:
            return
        try:
            self._mpv_player = mpv.MPV(
                wid=wid,
                input_default_bindings=True,
                input_vo_keyboard=True,
                log_handler=None,
            )
            self._mpv_player.loop_file = "inf" if self._loop_enabled else "no"
            self._mpv_player.speed = self._play_speed
            self._mpv_player.play(str(path))
            if pos > 0:
                self._mpv_player.seek(pos, reference="absolute")
            self._mpv_player.pause = paused
            self._video_playing = not paused
            self._set_play_icon()
        except Exception as exc:
            messagebox.showerror("Open video failed", f"mpv error: {exc}")

    def _get_render_target(self) -> tuple[ttk.Label | None, int, int]:
        if (
            self._fullscreen
            and self._fullscreen_panel is not None
            and self._fullscreen_label is not None
        ):
            w = self._fullscreen_panel.winfo_width()
            h = self._fullscreen_panel.winfo_height()
            return self._fullscreen_label, w, h
        if self._workspace is not None and self._video_label is not None:
            return (
                self._video_label,
                self._workspace.winfo_width(),
                self._workspace.winfo_height(),
            )
        return None, 0, 0

    def _fmt_time(self, seconds: float) -> str:
        secs = max(0, int(seconds))
        mins = secs // 60
        secs = secs % 60
        return f"{mins:02d}:{secs:02d}"

    def _draw_progress(self, ratio: float) -> None:
        if self._trackbar is not None:
            self._trackbar.draw_progress(ratio)
        if self._fs_trackbar is not None:
            self._fs_trackbar.draw_progress(ratio)

    def _set_time_labels(self, current: str, duration: str, duration_seconds: float) -> None:
        if self._trackbar is not None:
            self._trackbar.set_times(current, duration)
            self._trackbar.set_duration_seconds(duration_seconds)
        if self._fs_trackbar is not None:
            self._fs_trackbar.set_times(current, duration)
            self._fs_trackbar.set_duration_seconds(duration_seconds)

    def _seek_to_ratio(self, ratio: float, resume: bool = True) -> None:
        if self._mpv_player is not None:
            try:
                dur = float(self._mpv_player.duration or 0.0)
            except Exception:
                return
            if dur <= 0:
                return
            self._mpv_player.seek(dur * max(0.0, min(1.0, ratio)), reference="absolute")
            if resume:
                self._video_playing = True
            else:
                self._video_playing = False
                try:
                    self._mpv_player.pause = True
                except Exception:
                    pass
            self._set_play_icon()
            return
        if self._video_cap is None or self._total_frames <= 0:
            return
        target = int(max(0.0, min(1.0, ratio)) * self._total_frames)
        self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        self._play_start_ts = time.time()
        self._play_start_frame = target
        if resume:
            if not self._video_playing:
                self._video_playing = True
                self._set_play_icon()
                self._play_video()
        else:
            if self._video_playing:
                self._video_playing = False
                self._set_play_icon()
            self._preview_at_ratio(ratio)

    def _preview_at_ratio(self, ratio: float) -> None:
        if self._video_cap is None or self._total_frames <= 0:
            return
        target = int(max(0.0, min(1.0, ratio)) * self._total_frames)
        self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, frame = self._video_cap.read()
        if not ok or frame is None:
            return
        self._last_raw_frame = frame
        self._render_frame(frame)
