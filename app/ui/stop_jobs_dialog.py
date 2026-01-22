import tkinter as tk
from tkinter import messagebox, ttk

from app.core.recorder_manager import RecorderManager


class StopJobsDialog:
    def __init__(self, parent: tk.Misc, recorder_manager: RecorderManager) -> None:
        self.parent = parent
        self.recorder_manager = recorder_manager

    def open(
        self,
        names: list[str],
        title: str,
        on_done=None,
        show_done_message: bool = True,
    ) -> None:
        if not names:
            if on_done:
                on_done()
            return

        wait = tk.Toplevel(self.parent)
        wait.title(title)
        wait.configure(bg="white")
        wait.transient(self.parent)
        wait.grab_set()
        wait.resizable(False, False)

        screen_w = wait.winfo_screenwidth()
        screen_h = wait.winfo_screenheight()
        win_w = 380
        win_h = 170
        x = max(0, (screen_w - win_w) // 2)
        y = max(0, (screen_h - win_h) // 2)
        wait.geometry(f"{win_w}x{win_h}+{x}+{y}")

        ttk.Label(
            wait,
            text="Stopping jobs...\nPlease wait.",
            font=("Bai Jamjuree", 12, "bold"),
            background="white",
            foreground="#111827",
            justify="center",
        ).pack(padx=20, pady=(16, 6))

        current_var = tk.StringVar(value="Queued...")
        ttk.Label(
            wait,
            textvariable=current_var,
            font=("Bai Jamjuree", 11),
            background="white",
            foreground="#111827",
        ).pack(padx=20, pady=(0, 8))

        progress = ttk.Progressbar(
            wait, mode="determinate", maximum=len(names), length=320
        )
        progress.pack(padx=20, pady=(0, 16))

        for name in names:
            self.recorder_manager.queue_stop(name)

        def poll() -> None:
            active = set(self.recorder_manager.list_active())
            done = [n for n in names if n not in active]
            remaining = [n for n in names if n in active]
            progress["value"] = len(done)
            if remaining:
                current_var.set(f"Stopping: {remaining[0]}")
                wait.after(300, poll)
            else:
                if wait.winfo_exists():
                    wait.destroy()
                if show_done_message:
                    messagebox.showinfo("Recorder", "Saved successfully.")
                if on_done:
                    on_done()

        wait.after(200, poll)
