import cv2
import time
import threading
from ultralytics import YOLO

MODEL_PATH = "yolo26n.pt"
CAMERA_INDEX = 0
CONF_THRES = 0.5


class CameraStream:
    """Read camera in a thread and keep the latest frame (drop old frames)."""

    def __init__(self, src=0, width=None, height=None):
        self.src = src
        self.width = width
        self.height = height

        self.cap = None
        self.lock = threading.Lock()
        self.frame = None
        self.ok = False

        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        self._open()
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()
        return self

    def _open(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass

        self.cap = cv2.VideoCapture(self.src)

        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        if self.width is not None:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.width))
        if self.height is not None:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.height))

    def _reader(self):
        while not self.stop_event.is_set():
            if self.cap is None or not self.cap.isOpened():
                self._open()
                time.sleep(0.2)
                continue

            ok, frame = self.cap.read()
            if not ok or frame is None:
                with self.lock:
                    self.ok = False
                self._open()
                time.sleep(0.2)
                continue

            with self.lock:
                self.ok = True
                self.frame = frame

    def read(self):
        """Return (ok, frame_copy) to avoid race when thread updates."""
        with self.lock:
            if not self.ok or self.frame is None:
                return False, None
            return True, self.frame.copy()

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        if self.cap is not None:
            self.cap.release()


def main():
    model = YOLO(MODEL_PATH)
    stream = CameraStream(CAMERA_INDEX).start()

    prev_time = time.time()
    fps = 0.0

    try:
        while True:
            ok, frame = stream.read()
            if not ok:
                time.sleep(0.01)
                continue

            result = model.track(frame, persist=True, conf=CONF_THRES, verbose=False)[0]

            boxes = result.boxes
            if boxes is not None:
                xyxy = boxes.xyxy.cpu().numpy()
                conf = boxes.conf.cpu().numpy()
                cls = boxes.cls.cpu().numpy().astype(int)
                ids = (
                    boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None
                )

                for i, (x1, y1, x2, y2) in enumerate(xyxy):
                    c = conf[i]
                    k = cls[i]
                    if k != 0:
                        continue
                    x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    track_id = ids[i] if ids is not None else -1
                    label = f"id:{track_id} {c*100:.1f}%"
                    _draw_label(frame, label, x1, y1 - 6)

            now = time.time()
            inst_fps = 1.0 / max(1e-6, (now - prev_time))
            prev_time = now
            fps = 0.9 * fps + 0.1 * inst_fps

            _draw_label(frame, f"FPS: {fps:.1f}", 10, 30, bg=(0, 0, 0))

            cv2.imshow("Person (threaded)", frame)
            if cv2.waitKey(1) == ord("q"):
                break

    finally:
        stream.stop()
        cv2.destroyAllWindows()


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


if __name__ == "__main__":
    main()
