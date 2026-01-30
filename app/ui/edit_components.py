import tkinter as tk
from tkinter import ttk


class EditToolbar(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        on_open,
        on_trim,
        on_crop,
        on_save,
        *,
        bg: str = "#0f172a",
        width: int = 200,
    ) -> None:
        super().__init__(parent, bg=bg, width=width)
        self.pack_propagate(False)
        content = tk.Frame(self, bg=bg)
        content.pack(fill=tk.BOTH, expand=True)
        self._content = content
        self._open_btn = ttk.Button(
            content, text="Open File", command=on_open, style="Edit.Open.TButton"
        )
        self._open_btn.pack(fill=tk.X, padx=10, pady=(6, 0))
        self._bind_cursor(self._open_btn)

        self._trim_btn = ttk.Button(
            content,
            text="Trim",
            command=on_trim,
            style="Edit.Open.Disabled.TButton",
            state="disabled",
        )
        self._trim_btn.pack(fill=tk.X, padx=10, pady=(8, 0))
        self._bind_cursor(self._trim_btn)
        self._apply_toggle_button_style(self._trim_btn, enabled=False, on=False)

        self._crop_btn = ttk.Button(
            content,
            text="Crop",
            command=on_crop,
            style="Edit.Open.Disabled.TButton",
            state="disabled",
        )
        self._crop_btn.pack(fill=tk.X, padx=10, pady=(8, 0))
        self._bind_cursor(self._crop_btn)
        self._apply_toggle_button_style(self._crop_btn, enabled=False, on=False)

        self._save_btn = ttk.Button(
            content, text="Save", command=on_save, style="Edit.Open.TButton"
        )
        self._save_btn.pack(fill=tk.X, padx=10, pady=(10, 0))
        self._bind_cursor(self._save_btn)
        self._save_btn.pack_forget()
        self._save_visible = False

    def is_trim_enabled(self) -> bool:
        return str(self._trim_btn.cget("state")) != "disabled"

    def is_crop_enabled(self) -> bool:
        return str(self._crop_btn.cget("state")) != "disabled"

    def set_trim_state(self, enabled: bool, on: bool) -> None:
        self._trim_btn.configure(state="normal" if enabled else "disabled")
        self._apply_toggle_button_style(self._trim_btn, enabled=enabled, on=on)

    def set_crop_state(self, enabled: bool, on: bool) -> None:
        self._crop_btn.configure(state="normal" if enabled else "disabled")
        self._apply_toggle_button_style(self._crop_btn, enabled=enabled, on=on)

    def show_save(self, visible: bool) -> None:
        if visible and not self._save_visible:
            self._save_btn.pack(fill=tk.X, padx=10, pady=(10, 0))
            self._save_visible = True
        elif not visible and self._save_visible:
            self._save_btn.pack_forget()
            self._save_visible = False

    @staticmethod
    def _apply_toggle_button_style(
        button: ttk.Button, enabled: bool, on: bool
    ) -> None:
        if not enabled:
            button.configure(style="Edit.Open.Disabled.TButton")
            return
        if on:
            button.configure(style="Edit.Toggle.On.TButton")
        else:
            button.configure(style="Edit.Open.TButton")

    @staticmethod
    def _bind_cursor(button: ttk.Button) -> None:
        button.bind(
            "<Enter>",
            lambda _e: button.configure(
                cursor="hand2" if str(button.cget("state")) != "disabled" else "X_cursor"
            ),
        )
        button.bind("<Leave>", lambda _e: button.configure(cursor=""))


class PlaybackControls(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_play,
        on_stop,
        on_speed_down,
        on_speed_up,
        on_loop,
        on_fullscreen=None,
        font=("Font Awesome 6 Free Solid", 12),
        bg="#111111",
        tool_bg="#f8fafc",
        tool_hover="#dbeafe",
        tool_fg="#111827",
        loop_on_bg="#3b82f6",
        loop_on_fg="#ffffff",
        loop_on_hover="#2563eb",
        show_fullscreen: bool = True,
    ) -> None:
        super().__init__(parent, bg=bg)
        self._tool_bg = tool_bg
        self._tool_hover = tool_hover
        self._tool_fg = tool_fg
        self._loop_on_bg = loop_on_bg
        self._loop_on_fg = loop_on_fg
        self._loop_on_hover = loop_on_hover
        self._loop_enabled = False

        self.play_button = tk.Button(
            self,
            text="\uf04b",
            command=on_play,
            font=font,
            width=2,
            height=1,
            relief="flat",
            bg=tool_bg,
            activebackground=tool_hover,
            fg=tool_fg,
        )
        self.play_button.pack(side=tk.LEFT, padx=6, pady=2)
        self._bind_hover(self.play_button)

        self.stop_button = tk.Button(
            self,
            text="\uf04d",
            command=on_stop,
            font=font,
            width=2,
            height=1,
            relief="flat",
            bg=tool_bg,
            activebackground=tool_hover,
            fg="#dc2626",
            activeforeground="#dc2626",
        )
        self.stop_button.pack(side=tk.LEFT, padx=6, pady=2)
        self._bind_hover(self.stop_button)

        speed_down = tk.Button(
            self,
            text="\uf04a",
            command=on_speed_down,
            font=font,
            width=2,
            height=1,
            relief="flat",
            bg=tool_bg,
            activebackground=tool_hover,
            fg=tool_fg,
        )
        speed_down.pack(side=tk.LEFT, padx=(12, 0), pady=2)
        self._bind_hover(speed_down)

        speed_up = tk.Button(
            self,
            text="\uf04e",
            command=on_speed_up,
            font=font,
            width=2,
            height=1,
            relief="flat",
            bg=tool_bg,
            activebackground=tool_hover,
            fg=tool_fg,
        )
        speed_up.pack(side=tk.LEFT, padx=6, pady=2)
        self._bind_hover(speed_up)

        self.loop_button = tk.Button(
            self,
            text="\uf021",
            command=on_loop,
            font=font,
            width=2,
            height=1,
            relief="flat",
            bg=tool_bg,
            activebackground=tool_hover,
            fg=tool_fg,
        )
        self.loop_button.pack(side=tk.LEFT, padx=(12, 0), pady=2)
        self._bind_hover(self.loop_button)

        self.fullscreen_button = None
        if show_fullscreen and on_fullscreen is not None:
            self.fullscreen_button = tk.Button(
                self,
                text="\uf065",
                command=on_fullscreen,
                font=font,
                width=2,
                height=1,
                relief="flat",
                bg=tool_bg,
                activebackground=tool_hover,
                fg=tool_fg,
            )
            self.fullscreen_button.pack(side=tk.LEFT, padx=(12, 0), pady=2)
            self._bind_hover(self.fullscreen_button)

    def set_loop_enabled(self, enabled: bool) -> None:
        self._loop_enabled = enabled
        if self._loop_enabled:
            self.loop_button.configure(
                bg=self._loop_on_bg,
                fg=self._loop_on_fg,
                activebackground=self._loop_on_hover,
                activeforeground=self._loop_on_fg,
            )
        else:
            self.loop_button.configure(
                bg=self._tool_bg,
                fg=self._tool_fg,
                activebackground=self._tool_hover,
                activeforeground=self._tool_fg,
            )

    def _bind_hover(self, button: tk.Button) -> None:
        def on_enter(_e) -> None:
            if button == self.loop_button and self._loop_enabled:
                return
            button.configure(bg=self._tool_hover)

        def on_leave(_e) -> None:
            if button == self.loop_button and self._loop_enabled:
                return
            button.configure(bg=self._tool_bg)

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
