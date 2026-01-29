import time

import cv2

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.core.motion_detector import apply_motion, ensure_motion, get_motion_config

# SOURCE = 0  # Camera index or video path.
SOURCE = (
    "rtsp://admin:bvTTDCaps999@hcv08bwvjn5.sn.mynetname.net:555/Streaming/Channels/3701"
)
RESIZE = 0.5


def open_capture(source: str) -> cv2.VideoCapture:
    try:
        idx = int(source)
        return cv2.VideoCapture(idx)
    except ValueError:
        return cv2.VideoCapture(source)


def main() -> None:
    scale = max(0.1, min(1.0, float(RESIZE)))
    cap = open_capture(str(SOURCE))
    if not cap.isOpened():
        raise SystemExit("Cannot open source.")

    total_resize_ms = 0.0
    frames = 0
    last = time.perf_counter()
    fps_val = 0.0
    avg_resize_ms = 0.0
    avg_resize_fps = 0.0
    motion_ms_total = 0.0
    motion_frames = 0
    motion_avg_ms = 0.0
    motion_avg_fps = 0.0
    motion_state = {"bg": None}

    cv2.namedWindow("resize_perf", cv2.WINDOW_NORMAL)
    window_sized = False

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        resized = frame
        if scale < 1.0:
            t0 = time.perf_counter()
            new_w = int(frame.shape[1] * scale)
            new_h = int(frame.shape[0] * scale)
            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            total_resize_ms += dt_ms
        frames += 1

        config = get_motion_config()
        ensure_motion(motion_state, config)
        t_motion = time.perf_counter()
        boxes, _ = apply_motion(resized, motion_state, config)
        motion_ms = (time.perf_counter() - t_motion) * 1000.0
        motion_ms_total += motion_ms
        motion_frames += 1
        for x, y, w, h in boxes:
            cv2.rectangle(resized, (x, y), (x + w, y + h), (0, 200, 255), 2)

        now = time.perf_counter()
        inst_fps = 1.0 / max(1e-6, (now - last))
        last = now
        fps_val = 0.9 * fps_val + 0.1 * inst_fps
        if frames % 30 == 0:
            avg_resize_ms = total_resize_ms / max(1, frames if scale < 1.0 else 1)
            avg_resize_fps = 1000.0 / max(1e-6, avg_resize_ms) if scale < 1.0 else 0.0
            motion_avg_ms = motion_ms_total / max(1, motion_frames)
            motion_avg_fps = 1000.0 / max(1e-6, motion_avg_ms)

        info_lines = [
            f"FPS: {fps_val:.1f}",
            f"scale: {scale:.2f}",
            f"motion: {motion_avg_ms:.2f}ms ({motion_avg_fps:.1f} fps)",
        ]
        if scale < 1.0:
            resize_line = f"resize: {avg_resize_ms:.2f}ms ({avg_resize_fps:.1f} fps)"
        else:
            resize_line = "resize: n/a (scale=1.0)"
        info_lines.append(resize_line)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        thickness = 2
        line_h = 22
        margin = 8
        text_w = 0
        for line in info_lines:
            (tw, th), _ = cv2.getTextSize(line, font, font_scale, thickness)
            text_w = max(text_w, tw)
        box_w = text_w + margin * 2
        box_h = line_h * len(info_lines) + margin
        x0 = 8
        y0 = 8
        if resized.shape[0] < box_h + 16:
            y0 = max(0, resized.shape[0] - box_h - 8)
        cv2.rectangle(resized, (x0, y0), (x0 + box_w, y0 + box_h), (0, 0, 0), -1)
        for i, line in enumerate(info_lines):
            y = y0 + margin + (i + 1) * line_h - 6
            cv2.putText(
                resized,
                line,
                (x0 + margin, y),
                font,
                font_scale,
                (255, 255, 255),
                thickness,
            )

        if not window_sized:
            cv2.resizeWindow("resize_perf", resized.shape[1], resized.shape[0])
            window_sized = True
        cv2.imshow("resize_perf", resized)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
