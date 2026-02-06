import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import cv2
from PIL import Image, ImageTk

from app.config.models import CameraConfig
from app.core.stream_manager import StreamManager
from app.core.frame_store import FrameStore
from app.core.motion_detector import apply_motion, ensure_motion, get_motion_config
from app.utils.paths import get_pictures_dir

MODEL_PATH = "3103252.pt"
CONF_THRES = 0.7


def open_live_popup(
    parent: tk.Misc,
    camera: CameraConfig,
    stream_manager: StreamManager,
    frame_store: FrameStore,
) -> None:
    dialog = tk.Toplevel(parent)
    dialog.title(f"Live - {camera.name}")
    dialog.configure(bg="white")
    dialog.grab_set()
    dialog.transient(parent)
    dialog.resizable(False, False)

    width = 1280
    height = 720
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = 0
    dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    action_row = ttk.Frame(dialog)
    action_row.pack(fill=tk.X, padx=8, pady=(8, 0))

    stop_event = threading.Event()
    raw_frame = {"frame": None}
    display_frame = {"frame": None}
    frame_lock = threading.Lock()
    detect_enabled = tk.BooleanVar(value=False)
    motion_enabled = tk.BooleanVar(value=False)
    detector = {"model": None}
    motion_state = {"bg": None}
    motion_log = {"t": 0.0, "frames": 0, "ms": 0.0, "last": ""}
    prev_time = {"t": time.time()}
    fps_val = {"v": 0.0}
    resized_once = {"done": False}

    def capture_frame() -> None:
        with frame_lock:
            if detect_enabled.get() and display_frame["frame"] is not None:
                frame = display_frame["frame"]
            else:
                frame = raw_frame["frame"]
            frame = None if frame is None else frame.copy()
        if frame is None:
            return
        now = time.localtime()
        out_dir = (
            get_pictures_dir()
            / time.strftime("%Y", now)
            / time.strftime("%m", now)
            / time.strftime("%d", now)
            / camera.name
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%d-%m-%Y %Hh%Mm%Ss")
        out_path = out_dir / f"{camera.name} {ts}.jpg"
        cv2.imwrite(str(out_path), frame)
        messagebox.showinfo("Capture", f"Saved: {out_path}")

    def close_popup() -> None:
        stop_event.set()
        stream_manager.release(camera.name, "popup")
        dialog.destroy()

    ttk.Button(action_row, text="Capture", command=capture_frame).pack(
        side=tk.LEFT, padx=(0, 8)
    )
    ttk.Checkbutton(action_row, text="Detect", variable=detect_enabled).pack(
        side=tk.LEFT, padx=(12, 0)
    )
    ttk.Checkbutton(action_row, text="Motion", variable=motion_enabled).pack(
        side=tk.LEFT, padx=(12, 0)
    )
    ttk.Button(action_row, text="Exit", command=close_popup).pack(side=tk.RIGHT)

    video_label = ttk.Label(dialog)
    video_label.pack(padx=8, pady=8)

    def detect_loop() -> None:
        while not stop_event.is_set():
            if not detect_enabled.get() and not motion_enabled.get():
                time.sleep(0.02)
                continue
            with frame_lock:
                frame = None if raw_frame["frame"] is None else raw_frame["frame"].copy()
            if frame is None:
                time.sleep(0.01)
                continue
            if motion_enabled.get():
                t0 = time.perf_counter()
                config = get_motion_config()
                ensure_motion(motion_state, config)
                if motion_state["bg"] is None:
                    time.sleep(0.02)
                    continue
                boxes, fg = apply_motion(frame, motion_state, config)
                merged_box = _merge_boxes(boxes)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                now = time.time()
                motion_log["frames"] += 1
                motion_log["ms"] += dt_ms
                if now - motion_log["t"] > 1.0:
                    motion_log["t"] = now
                    avg_ms = motion_log["ms"] / max(1, motion_log["frames"])
                    avg_fps = 1000.0 / max(1e-6, avg_ms)
                    motion_log["frames"] = 0
                    motion_log["ms"] = 0.0
                    fg_count = int((fg > 0).sum()) if fg is not None else 0
                    motion_log["last"] = (
                        f"motion {avg_ms:.2f}ms ({avg_fps:.1f} fps) "
                        f"boxes:{len(boxes)} fg:{fg_count}"
                    )
                if motion_log["last"]:
                    _draw_label(
                        frame,
                        motion_log["last"],
                        10,
                        90,
                        bg=(0, 0, 0),
                        fg=(255, 255, 255),
                    )
                if merged_box:
                    x, y, w, h = merged_box
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 255), 2)
                    _draw_label(frame, "MOTION", 10, 60, bg=(0, 0, 0), fg=(0, 200, 255))
            if detect_enabled.get():
                _ensure_detector(detector)
                if detector["model"] is not None:
                    _apply_detection(frame, detector["model"])
            with frame_lock:
                display_frame["frame"] = frame
            time.sleep(0.01)

    stream_manager.acquire(camera.name, "popup")
    threading.Thread(target=detect_loop, daemon=True).start()

    def update_frame() -> None:
        if stop_event.is_set():
            return
        frame = frame_store.get_frame(camera.name)
        if frame is not None:
            frame = cv2.resize(frame, (1280, 720))
            with frame_lock:
                raw_frame["frame"] = frame
        with frame_lock:
            if detect_enabled.get() or motion_enabled.get():
                frame = display_frame["frame"]
            else:
                frame = raw_frame["frame"]
            frame = None if frame is None else frame.copy()
        if frame is not None:
            now = time.time()
            inst_fps = 1.0 / max(1e-6, (now - prev_time["t"]))
            prev_time["t"] = now
            fps_val["v"] = 0.9 * fps_val["v"] + 0.1 * inst_fps
            _draw_label(frame, f"FPS: {fps_val['v']:.1f}", 10, 30)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            photo = ImageTk.PhotoImage(img)
            video_label.configure(image=photo)
            video_label.image = photo
            if not resized_once["done"]:
                resized_once["done"] = True
                dialog.update_idletasks()
                req_w = dialog.winfo_reqwidth()
                req_h = dialog.winfo_reqheight()
                dialog.geometry(f"{req_w}x{req_h}+{max(0, x)}+{max(0, y)}")
        dialog.after(10, update_frame)

    dialog.protocol("WM_DELETE_WINDOW", close_popup)
    update_frame()


def _ensure_detector(state: dict) -> None:
    if state.get("model") is not None:
        return
    try:
        from ultralytics import YOLO

        state["model"] = YOLO(MODEL_PATH)
    except Exception as exc:
        state["model"] = None
        messagebox.showwarning("Detect", f"Model load failed: {exc}")


def _apply_detection(frame, model) -> None:
    result = model.track(frame, persist=True, conf=CONF_THRES, verbose=False)[0]
    boxes = result.boxes
    if boxes is None:
        return
    xyxy = boxes.xyxy.cpu().numpy()
    conf = boxes.conf.cpu().numpy()
    cls = boxes.cls.cpu().numpy().astype(int)
    ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None

    for i, (x1, y1, x2, y2) in enumerate(xyxy):
        if cls[i] != 0:
            continue
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        track_id = ids[i] if ids is not None else -1
        label = f"id:{track_id} {conf[i]*100:.1f}%"
        _draw_label(frame, label, x1, y1 - 6)


def _merge_boxes(boxes: list[tuple[int, int, int, int]] | None):
    if not boxes:
        return None
    x_min = min(b[0] for b in boxes)
    y_min = min(b[1] for b in boxes)
    x_max = max(b[0] + b[2] for b in boxes)
    y_max = max(b[1] + b[3] for b in boxes)
    return (x_min, y_min, max(1, x_max - x_min), max(1, y_max - y_min))


def _draw_label(frame, text, x, y, bg=(0, 0, 0), fg=(255, 255, 255)):
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    x = max(0, x)
    y = max(th + 4, y)
    cv2.rectangle(frame, (x, y - th - baseline - 4), (x + tw + 6, y + 2), bg, -1)
    cv2.putText(
        frame,
        text,
        (x + 3, y - 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        fg,
        2,
    )
