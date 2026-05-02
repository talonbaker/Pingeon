"""
Tkinter GUI for Photographer Monitor.

All monitoring runs in a background thread so the UI stays responsive.
The SMTP password lives only in a local variable inside _run_poll_loop()
and is cleared when monitoring stops.
"""

import os
import platform
import subprocess
import threading
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, scrolledtext, ttk
from typing import Optional

from . import config, email_notifier, logger, service_manager
from .calendar_poller import fetch_and_diff
from .constants import (
    APP_VERSION,
    MAX_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
)

# ── Colour palette ────────────────────────────────────────────────────────────
BG = "#1e1e2e"
BG2 = "#2a2a3e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
GREEN = "#a6e3a1"
RED = "#f38ba8"
YELLOW = "#f9e2af"
ENTRY_BG = "#313244"
BTN_BG = "#45475a"
BTN_ACTIVE = "#585b70"


class _PasswordDialog(tk.Toplevel):
    """Modal dialog that collects the Gmail password without ever saving it."""

    def __init__(self, parent: tk.Tk, email: str) -> None:
        super().__init__(parent)
        self.title("Email Password Required")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()

        self.result: Optional[str] = None

        pad = {"padx": 14, "pady": 6}

        tk.Label(
            self, text="Enter your Gmail password:", bg=BG, fg=FG, font=("Segoe UI", 10)
        ).pack(**pad)

        tk.Label(
            self, text=email, bg=BG, fg=ACCENT, font=("Segoe UI", 9, "italic")
        ).pack(padx=14, pady=(0, 6))

        self._var = tk.StringVar()
        pw_frame = tk.Frame(self, bg=BG)
        pw_frame.pack(padx=14, fill="x")

        self._entry = tk.Entry(
            pw_frame, textvariable=self._var, show="•",
            bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat",
            font=("Segoe UI", 11), width=28,
        )
        self._entry.pack(side="left", ipady=4)
        self._entry.focus_set()

        self._show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            pw_frame, text="Show", variable=self._show_var,
            command=self._toggle_show,
            bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            self,
            text="Password is NOT saved. It is only kept\nin memory while the monitor runs.",
            bg=BG, fg=YELLOW, font=("Segoe UI", 8), justify="center",
        ).pack(padx=14, pady=8)

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(pady=(0, 14))

        tk.Button(
            btn_frame, text="Start Monitor", command=self._confirm,
            bg=ACCENT, fg="#1e1e2e", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=12, pady=4, cursor="hand2",
            activebackground=BTN_ACTIVE, activeforeground=FG,
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame, text="Cancel", command=self.destroy,
            bg=BTN_BG, fg=FG, font=("Segoe UI", 10),
            relief="flat", padx=12, pady=4, cursor="hand2",
            activebackground=BTN_ACTIVE, activeforeground=FG,
        ).pack(side="left", padx=6)

        self.bind("<Return>", lambda _: self._confirm())
        self.bind("<Escape>", lambda _: self.destroy())

        # Centre over parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _toggle_show(self) -> None:
        self._entry.config(show="" if self._show_var.get() else "•")

    def _confirm(self) -> None:
        pw = self._var.get()
        if not pw:
            messagebox.showwarning("Password Required", "Please enter your password.", parent=self)
            return
        self.result = pw
        self.destroy()


class _LogViewer(tk.Toplevel):
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title("Monitor Logs")
        self.configure(bg=BG)
        self.geometry("640x420")

        self._text = scrolledtext.ScrolledText(
            self, bg=BG2, fg=FG, font=("Cascadia Code", 9),
            state="disabled", wrap="word",
        )
        self._text.pack(fill="both", expand=True, padx=8, pady=8)

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(pady=(0, 8))

        for text, cmd in [
            ("Refresh", self._refresh),
            ("Clear", self._clear),
            ("Open Full Log File", self._open_file),
        ]:
            tk.Button(
                btn_frame, text=text, command=cmd,
                bg=BTN_BG, fg=FG, relief="flat", padx=10, pady=3,
                activebackground=BTN_ACTIVE, activeforeground=FG,
                font=("Segoe UI", 9), cursor="hand2",
            ).pack(side="left", padx=4)

        self._refresh()

    def _refresh(self) -> None:
        lines = logger.get_recent_logs()
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("end", "\n".join(lines))
        self._text.see("end")
        self._text.config(state="disabled")

    def _clear(self) -> None:
        # Clear the visual display only; the file on disk is kept intact
        self._text.config(state="normal")
        self._text.delete("1.0", "end")
        self._text.config(state="disabled")

    def _open_file(self) -> None:
        path = logger.get_log_file_path()
        if not os.path.exists(path):
            messagebox.showinfo("Log File", "No log file created yet.", parent=self)
            return
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Photographer Monitor v{APP_VERSION}")
        self.configure(bg=BG)
        self.resizable(False, False)

        self._cfg = config.load()
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._password: Optional[str] = None   # never persisted

        self._build_ui()
        self._load_fields()
        self._update_status_label()

    # ── UI construction ───────────────────────────────────────────────────────

    def _label(self, parent, text: str, **kw) -> tk.Label:
        return tk.Label(parent, text=text, bg=BG, fg=FG, font=("Segoe UI", 9), **kw)

    def _entry(self, parent, textvariable: tk.StringVar, width: int = 46) -> tk.Entry:
        return tk.Entry(
            parent, textvariable=textvariable,
            bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat",
            font=("Segoe UI", 10), width=width,
        )

    def _btn(self, parent, text: str, command, colour: str = BTN_BG, **kw) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command,
            bg=colour, fg=FG if colour != ACCENT else "#1e1e2e",
            font=("Segoe UI", 10), relief="flat", cursor="hand2",
            activebackground=BTN_ACTIVE, activeforeground=FG,
            padx=10, pady=4, **kw,
        )

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 4}

        # ── Title
        tk.Label(
            self, text="Photographer Availability Monitor",
            bg=BG, fg=ACCENT, font=("Segoe UI", 13, "bold"),
        ).pack(pady=(14, 6))

        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="x", **pad)

        def row(label_text: str, widget_factory):
            self._label(frame, label_text).pack(anchor="w", pady=(6, 1))
            w = widget_factory()
            w.pack(anchor="w", ipady=3)
            return w

        # Calendar link
        self._cal_var = tk.StringVar()
        row("Calendar Link:", lambda: self._entry(frame, self._cal_var))

        # Date range
        date_frame = tk.Frame(frame, bg=BG)
        date_frame.pack(anchor="w", pady=(6, 0))
        self._label(date_frame, "Start Date (YYYY-MM-DD):").grid(row=0, column=0, sticky="w")
        self._label(date_frame, "End Date (YYYY-MM-DD):").grid(row=0, column=2, sticky="w", padx=(20, 0))
        self._start_var = tk.StringVar()
        self._end_var = tk.StringVar()
        tk.Entry(
            date_frame, textvariable=self._start_var,
            bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat",
            font=("Segoe UI", 10), width=14,
        ).grid(row=1, column=0, ipady=3, sticky="w")
        tk.Entry(
            date_frame, textvariable=self._end_var,
            bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat",
            font=("Segoe UI", 10), width=14,
        ).grid(row=1, column=2, ipady=3, sticky="w", padx=(20, 0))

        # Email
        self._email_var = tk.StringVar()
        row("Email Address:", lambda: self._entry(frame, self._email_var))

        # Interval
        interval_frame = tk.Frame(frame, bg=BG)
        interval_frame.pack(anchor="w", pady=(6, 0))
        self._label(interval_frame, "Check Interval (minutes):").pack(side="left")
        self._interval_var = tk.StringVar(value="2")
        tk.Spinbox(
            interval_frame, textvariable=self._interval_var,
            from_=MIN_INTERVAL_MINUTES, to=MAX_INTERVAL_MINUTES,
            width=5, bg=ENTRY_BG, fg=FG, buttonbackground=BTN_BG,
            relief="flat", font=("Segoe UI", 10),
        ).pack(side="left", padx=6, ipady=2)
        self._label(interval_frame, "(1–60 minutes recommended)").pack(side="left")

        # ── Action buttons
        sep = tk.Frame(self, bg=BG2, height=1)
        sep.pack(fill="x", padx=16, pady=10)

        action_frame = tk.Frame(self, bg=BG)
        action_frame.pack(**pad)

        self._btn(action_frame, "Save Settings", self._save_settings).grid(row=0, column=0, padx=4)
        self._btn(action_frame, "Test Alert", self._test_alert, colour=ACCENT).grid(row=0, column=1, padx=4)

        ctrl_frame = tk.Frame(self, bg=BG)
        ctrl_frame.pack(**pad)

        self._start_btn = self._btn(ctrl_frame, "Start Monitor", self._start_monitor, colour="#40a02b")
        self._start_btn.grid(row=0, column=0, padx=4)
        self._stop_btn = self._btn(ctrl_frame, "Stop Monitor", self._stop_monitor, colour="#d20f39")
        self._stop_btn.grid(row=0, column=1, padx=4)

        # ── Status bar
        sep2 = tk.Frame(self, bg=BG2, height=1)
        sep2.pack(fill="x", padx=16, pady=8)

        status_frame = tk.Frame(self, bg=BG)
        status_frame.pack(fill="x", padx=16, pady=(0, 6))
        self._label(status_frame, "Status:").pack(side="left")
        self._status_var = tk.StringVar(value="Not running")
        tk.Label(
            status_frame, textvariable=self._status_var,
            bg=BG, fg=RED, font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=6)
        self._label(status_frame, "  Last check:").pack(side="left")
        self._last_check_var = tk.StringVar(value="—")
        tk.Label(
            status_frame, textvariable=self._last_check_var,
            bg=BG, fg=FG, font=("Segoe UI", 9),
        ).pack(side="left", padx=6)

        # ── Bottom toolbar
        toolbar = tk.Frame(self, bg=BG2)
        toolbar.pack(fill="x", pady=(6, 0))
        for text, cmd in [
            ("View Logs", self._view_logs),
            ("About", self._about),
        ]:
            self._btn(toolbar, text, cmd, colour=BG2).pack(side="left", padx=4, pady=4)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Field helpers ─────────────────────────────────────────────────────────

    def _load_fields(self) -> None:
        self._cal_var.set(self._cfg.get("calendar_link", ""))
        self._start_var.set(self._cfg.get("monitor_start_date", ""))
        self._end_var.set(self._cfg.get("monitor_end_date", ""))
        self._email_var.set(self._cfg.get("email_address", ""))
        self._interval_var.set(str(self._cfg.get("check_interval_minutes", 2)))

    def _fields_to_cfg(self) -> dict:
        return {
            "calendar_link": self._cal_var.get().strip(),
            "calendar_id": "",
            "monitor_start_date": self._start_var.get().strip(),
            "monitor_end_date": self._end_var.get().strip(),
            "email_address": self._email_var.get().strip(),
            "check_interval_minutes": self._interval_var.get().strip(),
        }

    # ── Button handlers ───────────────────────────────────────────────────────

    def _save_settings(self) -> None:
        draft = self._fields_to_cfg()
        errors = config.validate(draft)
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors), parent=self)
            return
        try:
            draft["calendar_id"] = config.extract_calendar_id(draft["calendar_link"])
            draft["check_interval_minutes"] = int(draft["check_interval_minutes"])
            config.save(draft)
            self._cfg = draft
            messagebox.showinfo("Saved", "Settings saved successfully.", parent=self)
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc), parent=self)

    def _test_alert(self) -> None:
        draft = self._fields_to_cfg()
        errors = config.validate(draft)
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors), parent=self)
            return

        dlg = _PasswordDialog(self, draft["email_address"])
        self.wait_window(dlg)
        if not dlg.result:
            return

        password = dlg.result
        try:
            email_notifier.send_test_email(draft["email_address"], password)
            messagebox.showinfo("Test Email", "Test email sent! Check your inbox.", parent=self)
        except Exception as exc:
            messagebox.showerror("Email Error", str(exc), parent=self)
        finally:
            password = ""  # discard immediately

    def _start_monitor(self) -> None:
        if service_manager.is_running():
            messagebox.showinfo("Already Running", "Monitor is already running.", parent=self)
            return

        # Validate and save first
        draft = self._fields_to_cfg()
        errors = config.validate(draft)
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors), parent=self)
            return

        if not self._cfg.get("calendar_id"):
            try:
                draft["calendar_id"] = config.extract_calendar_id(draft["calendar_link"])
                draft["check_interval_minutes"] = int(draft["check_interval_minutes"])
                config.save(draft)
                self._cfg = draft
            except Exception as exc:
                messagebox.showerror("Config Error", str(exc), parent=self)
                return

        dlg = _PasswordDialog(self, self._cfg["email_address"])
        self.wait_window(dlg)
        if not dlg.result:
            return

        self._password = dlg.result
        self._stop_event.clear()
        service_manager.set_running(True)
        self._update_status_label()

        self._poll_thread = threading.Thread(
            target=self._run_poll_loop, daemon=True
        )
        self._poll_thread.start()
        logger.info("Monitor started.")

    def _stop_monitor(self) -> None:
        if not service_manager.is_running():
            return
        self._stop_event.set()
        service_manager.set_running(False)
        self._password = None
        self._update_status_label()
        logger.info("Monitor stopped.")

    # ── Polling loop (background thread) ─────────────────────────────────────

    def _run_poll_loop(self) -> None:
        cfg = self._cfg
        calendar_id = cfg["calendar_id"]
        start_date = date.fromisoformat(cfg["monitor_start_date"])
        end_date = date.fromisoformat(cfg["monitor_end_date"])
        email = cfg["email_address"]
        interval_seconds = int(cfg["check_interval_minutes"]) * 60
        password = self._password  # local copy; cleared on stop

        while not self._stop_event.is_set():
            try:
                logger.info("Checking calendar…")
                cancelled = fetch_and_diff(calendar_id, start_date, end_date)
                self._update_last_check()

                if cancelled and password:
                    email_notifier.send_alert_email(email, password, cancelled)

            except Exception as exc:
                logger.error(f"Poll error: {exc}")

            # Sleep in small increments so stop_event is detected promptly
            for _ in range(interval_seconds):
                if self._stop_event.is_set():
                    break
                import time
                time.sleep(1)

        password = None  # ensure it doesn't linger in this frame

    def _update_last_check(self) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.after(0, lambda: self._last_check_var.set(ts))

    def _update_status_label(self) -> None:
        if service_manager.is_running():
            self._status_var.set("Running")
            # find and recolour the status label
            for widget in self.winfo_children():
                _recolour_status(widget, GREEN)
        else:
            self._status_var.set("Not running")
            for widget in self.winfo_children():
                _recolour_status(widget, RED)

    # ── Misc handlers ─────────────────────────────────────────────────────────

    def _view_logs(self) -> None:
        _LogViewer(self)

    def _about(self) -> None:
        messagebox.showinfo(
            "About",
            f"Photographer Monitor v{APP_VERSION}\n\n"
            "Monitors a photographer's public Google Calendar for cancellations "
            "and alerts you via email.\n\n"
            "All data stays on your machine. Only Google Calendar ICS feeds and "
            "Gmail SMTP are contacted externally.\n\n"
            "MIT License — Talon Baker",
            parent=self,
        )

    def _on_close(self) -> None:
        if service_manager.is_running():
            if messagebox.askyesno(
                "Stop Monitor?",
                "The monitor is still running. Stop it and close?",
                parent=self,
            ):
                self._stop_monitor()
                self.destroy()
        else:
            self.destroy()


def _recolour_status(widget: tk.Widget, colour: str) -> None:
    """Recursively find and recolour status label in the widget tree."""
    try:
        if isinstance(widget, tk.Label) and "Running" in (widget.cget("textvariable") or ""):
            widget.config(fg=colour)
    except Exception:
        pass
    for child in widget.winfo_children():
        _recolour_status(child, colour)


def run() -> None:
    app = App()
    app.mainloop()
