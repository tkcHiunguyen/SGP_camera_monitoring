from __future__ import annotations

from typing import Callable
import tkinter as tk
from tkinter import ttk


class EmptyState(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        message: str,
        icon: str = "\uf03d",
        action_text: str | None = None,
        action: Callable[[], None] | None = None,
        variant: str = "light",
    ) -> None:
        super().__init__(parent, style="App.TFrame")
        self._variant = variant
        self._colors = self._resolve_colors(variant)
        self._icon = icon
        self._build_ui(title, message, action_text, action)

    def _resolve_colors(self, variant: str) -> dict[str, str]:
        style = ttk.Style(self)
        base_bg = style.lookup("App.TFrame", "background") or "#f7f4ef"
        if variant == "dark":
            style.configure("Empty.Dark.TFrame", background="#0f172a")
            return {
                "bg": "#0f172a",
                "fg": "#e5e7eb",
                "muted": "#94a3b8",
                "accent": "#60a5fa",
                "accent_soft": "#1e293b",
                "surface": "#111827",
                "border": "#1f2937",
            }
        return {
            "bg": base_bg if isinstance(base_bg, str) else "#f7f4ef",
            "fg": "#0f172a",
            "muted": "#6b7280",
            "accent": "#2563eb",
            "accent_soft": "#dbeafe",
            "surface": "#ffffff",
            "border": "#e2e8f0",
        }

    def _build_ui(
        self,
        title: str,
        message: str,
        action_text: str | None,
        action: callable | None,
    ) -> None:
        frame_style = "Empty.Dark.TFrame" if self._variant == "dark" else "App.TFrame"
        self.configure(style=frame_style)
        self.configure(padding=(12, 10))

        art = tk.Canvas(
            self,
            width=260,
            height=160,
            highlightthickness=0,
            bg=self._colors["bg"],
        )
        art.pack(pady=(18, 8))

        self._draw_illustration(art, self._colors, self._icon)

        title_label = ttk.Label(
            self,
            text=title,
            font=("Bai Jamjuree", 14, "bold"),
            foreground=self._colors["fg"],
            background=self._colors["bg"],
        )
        title_label.pack()

        message_label = ttk.Label(
            self,
            text=message,
            font=("Bai Jamjuree", 11),
            foreground=self._colors["muted"],
            background=self._colors["bg"],
            justify="center",
        )
        message_label.pack(pady=(6, 12))

        if action_text and action:
            btn_style = (
                "App.Toolbar.Accent.TButton" if self._variant == "light" else "App.Toolbar.TButton"
            )
            ttk.Button(
                self,
                text=action_text,
                command=action,
                style=btn_style,
            ).pack(pady=(0, 12))

    def _draw_illustration(self, canvas: tk.Canvas, colors: dict[str, str], icon: str) -> None:
        canvas.create_oval(16, 22, 132, 138, fill=colors["accent_soft"], outline="")
        canvas.create_oval(38, 8, 112, 72, fill=colors["surface"], outline=colors["border"])
        canvas.create_rectangle(110, 28, 242, 120, fill=colors["surface"], outline=colors["border"], width=2)
        canvas.create_rectangle(132, 48, 220, 94, fill=colors["accent_soft"], outline="")
        canvas.create_oval(146, 58, 176, 88, fill=colors["bg"], outline=colors["border"])
        canvas.create_oval(182, 58, 212, 88, fill=colors["bg"], outline=colors["border"])

        canvas.create_text(
            92,
            98,
            text=icon,
            font=("Font Awesome 6 Free Solid", 40),
            fill=colors["accent"],
        )
