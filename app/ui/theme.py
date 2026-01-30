from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class Theme:
    font_body: tuple = ("Bai Jamjuree", 12)
    font_body_bold: tuple = ("Bai Jamjuree", 12, "bold")
    font_title: tuple = ("Bai Jamjuree", 14, "bold")
    fg: str = "#111827"
    muted: str = "#6b7280"
    bg: str = "#f7f4ef"
    border: str = "#e5e7eb"
    accent: str = "#2563eb"
    success: str = "#16a34a"
    warning: str = "#f59e0b"
    danger: str = "#dc2626"


def apply_theme(root: tk.Misc, theme: Theme | None = None) -> Theme:
    theme = theme or Theme()
    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass

    style.configure("App.TFrame", background=theme.bg)
    style.configure(
        "App.TLabel", background=theme.bg, foreground=theme.fg, font=theme.font_body
    )
    style.configure(
        "App.Title.TLabel",
        background=theme.bg,
        foreground=theme.fg,
        font=theme.font_title,
    )
    style.configure(
        "App.Toolbar.TButton",
        font=theme.font_body,
        padding=(10, 4),
    )
    style.configure(
        "App.Toolbar.Accent.TButton",
        font=theme.font_body_bold,
        padding=(10, 4),
    )
    style.map(
        "App.Toolbar.Accent.TButton",
        foreground=[("active", theme.bg)],
        background=[("active", theme.accent)],
    )
    style.configure(
        "App.Toolbar.AccentText.TButton",
        font=theme.font_body_bold,
        padding=(10, 4),
        foreground=theme.accent,
        background=theme.bg,
    )
    style.map(
        "App.Toolbar.AccentText.TButton",
        foreground=[("active", theme.accent)],
        background=[("active", "#e2e8f0")],
    )

    style.configure("App.Menu.TFrame", background=theme.bg)
    style.configure(
        "App.Menu.TButton",
        font=theme.font_body_bold,
        padding=(14, 6),
        background=theme.bg,
        foreground=theme.fg,
    )
    style.map(
        "App.Menu.TButton",
        background=[("active", "#e2e8f0")],
        foreground=[("active", "#0f172a")],
    )
    style.configure(
        "App.Menu.Active.TButton",
        font=theme.font_body_bold,
        padding=(14, 6),
        background=theme.border,
        foreground=theme.accent,
    )
    style.map(
        "App.Menu.Active.TButton",
        background=[("active", theme.border)],
        foreground=[("active", theme.accent)],
    )

    style.configure(
        "Modal.TFrame",
        background=theme.bg,
    )
    style.configure(
        "Modal.TLabel",
        background=theme.bg,
        foreground=theme.fg,
        font=theme.font_body,
    )
    style.configure(
        "Modal.TLabelframe",
        background=theme.bg,
    )
    style.configure(
        "Modal.TLabelframe.Label",
        background=theme.bg,
        foreground=theme.fg,
        font=theme.font_body_bold,
    )
    style.configure(
        "Modal.TRadiobutton",
        background=theme.bg,
        foreground=theme.fg,
        font=theme.font_body,
    )
    style.configure("Modal.TButton", font=theme.font_body)
    style.configure(
        "Modal.TCombobox",
        padding=(8, 6),
        font=("Bai Jamjuree", 13),
    )
    style.map(
        "Modal.TCombobox",
        fieldbackground=[("readonly", "#f3f4f6")],
        background=[("readonly", "#f3f4f6")],
    )
    style.configure("Modal.TNotebook", background=theme.bg)
    style.configure("Modal.TNotebook.Tab", font=theme.font_body_bold)

    _configure_treeview(style, theme)
    return theme


def _configure_treeview(style: ttk.Style, theme: Theme) -> None:
    style.configure(
        "App.Treeview",
        font=theme.font_body,
        rowheight=28,
    )
    style.configure(
        "App.Treeview.Heading",
        font=theme.font_body_bold,
    )
