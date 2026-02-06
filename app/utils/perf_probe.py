import csv
import os
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import psutil  # type: ignore
except Exception:
    psutil = None


class PerfProbe:
    """Lightweight perf logger; safe to remove if unused."""

    def __init__(
        self,
        tag: str,
        interval_s: float = 5.0,
        out_dir: Optional[Path] = None,
    ) -> None:
        self.tag = tag
        self.interval_s = max(0.5, float(interval_s))
        self.out_dir = out_dir or Path("perf_logs")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        safe_tag = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tag)
        self.path = self.out_dir / f"perf_{safe_tag}.csv"
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._counters = {
            "grabbed": 0,
            "decoded": 0,
            "queued": 0,
            "dropped": 0,
            "written": 0,
            "motion": 0,
            "queue_size": 0,
            "fps": 0.0,
        }
        self._init_csv()

    def _init_csv(self) -> None:
        if self.path.exists():
            return
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "ts",
                    "tag",
                    "cpu_pct",
                    "rss_mb",
                    "grabbed",
                    "decoded",
                    "queued",
                    "dropped",
                    "written",
                    "motion",
                    "queue_size",
                    "fps",
                ]
            )

    def record_capture(
        self,
        *,
        grabbed: int = 0,
        decoded: int = 0,
        queued: int = 0,
        dropped: int = 0,
        queue_size: int = 0,
    ) -> None:
        self._record(
            grabbed=grabbed,
            decoded=decoded,
            queued=queued,
            dropped=dropped,
            queue_size=queue_size,
        )

    def record_write(
        self,
        *,
        written: int = 0,
        motion: int = 0,
        fps: float = 0.0,
        queue_size: int = 0,
    ) -> None:
        self._record(
            written=written,
            motion=motion,
            fps=fps,
            queue_size=queue_size,
        )

    def _record(self, **updates) -> None:
        now = time.time()
        with self._lock:
            for key, value in updates.items():
                if key not in self._counters:
                    continue
                if isinstance(value, (int, float)):
                    if key in ("queue_size", "fps"):
                        self._counters[key] = value
                    else:
                        self._counters[key] += int(value)
            if now - self._last_flush >= self.interval_s:
                self._flush(now)

    def _flush(self, now: float) -> None:
        cpu_pct = ""
        rss_mb = ""
        if psutil is not None:
            try:
                proc = psutil.Process(os.getpid())
                cpu_pct = f"{proc.cpu_percent(interval=None):.1f}"
                rss_mb = f"{proc.memory_info().rss / (1024 * 1024):.1f}"
            except Exception:
                cpu_pct = ""
                rss_mb = ""
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    f"{now:.3f}",
                    self.tag,
                    cpu_pct,
                    rss_mb,
                    self._counters["grabbed"],
                    self._counters["decoded"],
                    self._counters["queued"],
                    self._counters["dropped"],
                    self._counters["written"],
                    self._counters["motion"],
                    self._counters["queue_size"],
                    f"{self._counters['fps']:.2f}",
                ]
            )
        for key in ("grabbed", "decoded", "queued", "dropped", "written", "motion"):
            self._counters[key] = 0
        self._last_flush = now
