"""
Tkinter GUI for Pingeon.

Users provide the email address they want alerts sent TO.
No password. No credentials. Pingeon's relay handles the sending.
"""

import os
import platform
import subprocess
import threading
import time
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, scrolledtext
from typing import Optional

from . import config, logger, service_manager
from .calendar_poller import fetch_and_diff
from .notifier import send_alert, send_test
from .constants import APP_VERSION, MIN_INTERVAL_MINUTES, MAX_INTERVAL_MINUTES

BG       = "#1e1e2e"
BG2      = "#2a2a3e"
FG       = "#cdd6f4"
ACCENT   = "#89b4fa"
GREEN    = "#a6e3a1"
RED      = "#f38ba8"
YELLOW   = "#f9e2af"
ENTRY_BG = "#313244"
BTN_BG   = "#45475a"
BTN_ACT  = "#585b70"


class _LogViewer(tk.Toplevel):
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title("Pingeon — Logs")
        self.configure(bg=BG)
        self.geometry("680x440")

        self._text = scrolledtext.ScrolledText(
            self, bg=BG2, fg=FG, font=("Cascadia Code", 9),
            state="disabled", wrap="word",
        )
        self._text.pack(fill="both", expand=True, padx=8, pady=8)

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(pady=(0, 8))
        for text, cmd in [("Refresh", self._refresh), ("Open Log File", self._open_file)]:
            tk.Button(
                btn_frame, text=text, command=cmd,
                bg=BTN_BG, fg=FG, relief="flat", padx=10, pady=3,
                activebackground=BTN_ACT, activeforeground=FG,
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
        self.title(f"Pingeon v{APP_VERSION}")
        self.configure(bg=BG)
        self.resizable(False, False)

        self._cfg = config.load()
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._build_ui()
        self._load_fields()
        self._refresh_status()

    # ── UI construction ───────────────────────────────────────────────────────

    def _lbl(self, parent, text, **kw) -> tk.Label:
        return tk.Label(parent, text=text, bg=BG, fg=FG, font=("Segoe UI", 9), **kw)

    def _entry(self, parent, var, width=50) -> tk.Entry:
        return tk.Entry(
            parent, textvariable=var,
            bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat",
            font=("Segoe UI", 10), width=width,
        )

    def _btn(self, parent, text, cmd, colour=BTN_BG, fg=FG, **kw) -> tk.Button:
        return tk.Button(
            parent, text=text, command=cmd,
            bg=colour, fg=fg, font=("Segoe UI", 10),
            relief="flat", cursor="hand2",
            activebackground=BTN_ACT, activeforeground=FG,
            padx=10, pady=4, **kw,
        )

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 4}

        tk.Label(
            self, text="Pingeon — Calendar Monitor",
            bg=BG, fg=ACCENT, font=("Segoe UI", 13, "bold"),
        ).pack(pady=(14, 8))

        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="x", **pad)

        # Calendar link
        self._cal_var = tk.StringVar()
        self._lbl(frame, "Calendar Link:").pack(anchor="w", pady=(4, 1))
        self._entry(frame, self._cal_var).pack(anchor="w", ipady=3)

        # Date range
        dr = tk.Frame(frame, bg=BG)
        dr.pack(anchor="w", pady=(8, 0))
        self._lbl(dr, "Start Date (YYYY-MM-DD):").grid(row=0, column=0, sticky="w")
        self._lbl(dr, "End Date (YYYY-MM-DD):").grid(row=0, column=2, sticky="w", padx=(20, 0))
        self._start_var = tk.StringVar()
        self._end_var = tk.StringVar()
        for col, var in ((0, self._start_var), (2, self._end_var)):
            tk.Entry(
                dr, textvariable=var,
                bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat",
                font=("Segoe UI", 10), width=14,
            ).grid(row=1, column=col, ipady=3, sticky="w",
                   padx=(0 if col == 0 else 20, 0))

        # Interval
        iv = tk.Frame(frame, bg=BG)
        iv.pack(anchor="w", pady=(8, 0))
        self._lbl(iv, "Check Interval (minutes):").pack(side="left")
        self._interval_var = tk.StringVar(value="2")
        tk.Spinbox(
            iv, textvariable=self._interval_var,
            from_=MIN_INTERVAL_MINUTES, to=MAX_INTERVAL_MINUTES,
            width=5, bg=ENTRY_BG, fg=FG, buttonbackground=BTN_BG,
            relief="flat", font=("Segoe UI", 10),
        ).pack(side="left", padx=6, ipady=2)

        # Alert email — the address that RECEIVES alerts (user does not send)
        self._lbl(frame, "Alert Email:").pack(anchor="w", pady=(10, 1))
        self._email_var = tk.StringVar()
        self._entry(frame, self._email_var).pack(anchor="w", ipady=3)
        self._lbl(
            frame,
            "Pingeon will send alerts to this address. No password required.",
            fg=YELLOW,
        ).pack(anchor="w")

        # ── Buttons
        tk.Frame(self, bg=BG2, height=1).pack(fill="x", padx=16, pady=10)

        row1 = tk.Frame(self, bg=BG)
        row1.pack(**pad)
        self._btn(row1, "Save Settings", self._save).grid(row=0, column=0, padx=4)
        self._btn(row1, "Send Test Alert", self._test_alert, colour=ACCENT, fg="#1e1e2e").grid(row=0, column=1, padx=4)

        row2 = tk.Frame(self, bg=BG)
        row2.pack(**pad)
        self._start_btn = self._btn(row2, "Start Monitor", self._start, colour="#40a02b")
        self._start_btn.grid(row=0, column=0, padx=4)
        self._stop_btn = self._btn(row2, "Stop Monitor", self._stop, colour="#d20f39")
        self._stop_btn.grid(row=0, column=1, padx=4)

        # Status bar
        tk.Frame(self, bg=BG2, height=1).pack(fill="x", padx=16, pady=8)
        sf = tk.Frame(self, bg=BG)
        sf.pack(fill="x", padx=16, pady=(0, 6))
        self._lbl(sf, "Status:").pack(side="left")
        self._status_var = tk.StringVar(value="Not running")
        self._status_lbl = tk.Label(
            sf, textvariable=self._status_var,
            bg=BG, fg=RED, font=("Segoe UI", 10, "bold"),
        )
        self._status_lbl.pack(side="left", padx=6)
        self._lbl(sf, "  Last check:").pack(side="left")
        self._last_check_var = tk.StringVar(value="—")
        tk.Label(sf, textvariable=self._last_check_var, bg=BG, fg=FG,
                 font=("Segoe UI", 9)).pack(side="left", padx=4)

        # Toolbar
        tb = tk.Frame(self, bg=BG2)
        tb.pack(fill="x", pady=(6, 0))
        for text, cmd in [("View Logs", self._view_logs), ("About", self._about)]:
            self._btn(tb, text, cmd, colour=BG2).pack(side="left", padx=4, pady=4)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_fields(self) -> None:
        self._cal_var.set(self._cfg.get("calendar_link", ""))
        self._start_var.set(self._cfg.get("monitor_start_date", ""))
        self._end_var.set(self._cfg.get("monitor_end_date", ""))
        self._interval_var.set(str(self._cfg.get("check_interval_minutes", 2)))
        self._email_var.set(self._cfg.get("alert_email", ""))

    def _fields_to_draft(self) -> dict:
        return {
            "calendar_link": self._cal_var.get().strip(),
            "calendar_id": self._cfg.get("calendar_id", ""),
            "monitor_start_date": self._start_var.get().strip(),
            "monitor_end_date": self._end_var.get().strip(),
            "check_interval_minutes": self._interval_var.get().strip(),
            "alert_email": self._email_var.get().strip(),
        }

    def _refresh_status(self) -> None:
        if service_manager.is_running():
            self._status_var.set("Running")
            self._status_lbl.config(fg=GREEN)
        else:
            self._status_var.set("Not running")
            self._status_lbl.config(fg=RED)

    # ── Button handlers ───────────────────────────────────────────────────────

    def _save(self) -> None:
        draft = self._fields_to_draft()
        errors = config.validate(draft)
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors), parent=self)
            return
        try:
            draft["calendar_id"] = config.extract_calendar_id(draft["calendar_link"])
            draft["check_interval_minutes"] = int(draft["check_interval_minutes"])
            config.save(draft)
            self._cfg = draft
            messagebox.showinfo("Saved", "Settings saved.", parent=self)
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc), parent=self)

    def _test_alert(self) -> None:
        draft = self._fields_to_draft()
        email = draft.get("alert_email", "").strip()
        if not email:
            messagebox.showwarning("No Email", "Enter an alert email address first.", parent=self)
            return
        try:
            send_test(email)
            messagebox.showinfo(
                "Test Sent",
                f"Test alert sent to {email}.\nCheck your inbox (and spam folder).",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Alert Error", str(exc), parent=self)

    def _start(self) -> None:
        if service_manager.is_running():
            messagebox.showinfo("Already Running", "Monitor is already running.", parent=self)
            return

        draft = self._fields_to_draft()
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

        self._stop_event.clear()
        service_manager.set_running(True)
        self._refresh_status()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("Monitor started.")

    def _stop(self) -> None:
        if not service_manager.is_running():
            return
        self._stop_event.set()
        service_manager.set_running(False)
        self._refresh_status()
        logger.info("Monitor stopped.")

    # ── Poll loop (background thread) ─────────────────────────────────────────

    def _poll_loop(self) -> None:
        cfg = self._cfg
        calendar_id = cfg["calendar_id"]
        start_date = date.fromisoformat(cfg["monitor_start_date"])
        end_date = date.fromisoformat(cfg["monitor_end_date"])
        alert_email = cfg["alert_email"]
        interval_seconds = int(cfg["check_interval_minutes"]) * 60

        while not self._stop_event.is_set():
            try:
                logger.info("Checking calendar…")
                opened = fetch_and_diff(calendar_id, start_date, end_date)
                self.after(0, lambda: self._last_check_var.set(
                    datetime.now().strftime("%H:%M:%S")
                ))
                if opened:
                    try:
                        send_alert(alert_email, opened)
                    except Exception as exc:
                        logger.error(f"Could not send alert email: {exc}")
                    # Always show in-app dialog too
                    slots = "\n".join(f"• {e.label()}" for e in opened)
                    self.after(0, lambda s=slots: messagebox.showinfo(
                        "Pingeon — Slot Available!",
                        f"A slot just opened:\n\n{s}\n\n"
                        f"An alert email was sent to {alert_email}.",
                        parent=self,
                    ))
            except Exception as exc:
                logger.error(f"Poll error: {exc}")

            for _ in range(interval_seconds):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _view_logs(self) -> None:
        _LogViewer(self)

    def _about(self) -> None:
        messagebox.showinfo(
            "About Pingeon",
            f"Pingeon v{APP_VERSION}\n\n"
            "Watches any public Google Calendar for cancellations and emails you "
            "the moment a slot opens.\n\n"
            "External connections:\n"
            "  • Google Calendar ICS feed (read-only)\n"
            "  • Pingeon relay (sends your alert email)\n\n"
            "Everything else stays on your machine.\n"
            "MIT License",
            parent=self,
        )

    def _on_close(self) -> None:
        if service_manager.is_running():
            if messagebox.askyesno("Stop Monitor?",
                                   "Monitor is running. Stop it and close?", parent=self):
                self._stop()
                self.destroy()
        else:
            self.destroy()


def run() -> None:
    App().mainloop()
