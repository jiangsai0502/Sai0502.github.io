#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import font
from zoneinfo import ZoneInfo

try:
    import AppKit
except Exception:
    AppKit = None

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "reminder.log"
DEFAULT_CONFIG = {
    "times": ["21:25"],
    "quotes_file": "quotes.txt",
    "message": "并非每天都有绝佳的机会，没有就空仓一天",
    "title": "交易前提醒",
    "timezone": "Asia/Shanghai",
    "allow_weekends": True,
    "snooze_seconds_after_success": 60,
    "keep_front_seconds": 3,
}


def log(line):
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {line}\n")


def load_config():
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    config = DEFAULT_CONFIG.copy()
    config.update(data)
    return config


def load_quotes(config):
    quotes_file = config.get("quotes_file")
    if not quotes_file:
        return []
    path = Path(quotes_file)
    if not path.is_absolute():
        path = APP_DIR / path
    if not path.exists():
        log(f"quotes file not found: {path}")
        return []
    quotes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            quotes.append(text)
    return quotes


def daily_message(config, when=None):
    quotes = load_quotes(config)
    if not quotes:
        return config.get("message", DEFAULT_CONFIG["message"])

    tz = ZoneInfo(config.get("timezone", "Asia/Shanghai"))
    today = when.astimezone(tz).date() if when else dt.datetime.now(tz).date()
    seed_text = f"{today.isoformat()}|{config.get('quotes_file', '')}"
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    index = int(digest[:12], 16) % len(quotes)
    return quotes[index]


def parse_time(value):
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


def next_fire_time(config):
    tz = ZoneInfo(config.get("timezone", "Asia/Shanghai"))
    now = dt.datetime.now(tz)
    candidates = []
    for time_text in config["times"]:
        hour, minute = parse_time(time_text)
        for day_offset in range(0, 8):
            candidate = (now + dt.timedelta(days=day_offset)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if candidate <= now:
                continue
            if not config.get("allow_weekends", True) and candidate.weekday() >= 5:
                continue
            candidates.append(candidate)
    if not candidates:
        tomorrow = now + dt.timedelta(days=1)
        hour, minute = parse_time(config["times"][0])
        return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return min(candidates)


def activate_app():
    if AppKit is not None:
        try:
            app = AppKit.NSRunningApplication.currentApplication()
            app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        except Exception as exc:
            log(f"activateWithOptions failed: {exc}")


def screen_geometries():
    if AppKit is None:
        return []
    try:
        screens = AppKit.NSScreen.screens()
        main_frame = AppKit.NSScreen.mainScreen().frame()
        geoms = []
        for screen in screens:
            frame = screen.frame()
            x = int(frame.origin.x)
            width = int(frame.size.width)
            height = int(frame.size.height)
            # Tk uses top-left origin. Cocoa uses bottom-left origin.
            y = int(main_frame.size.height - frame.origin.y - frame.size.height)
            geoms.append((x, y, width, height))
        return geoms
    except Exception as exc:
        log(f"screen geometry failed: {exc}")
        return []


class ReminderOverlay:
    def __init__(self, config):
        self.config = config
        self.message = config["message"]
        self.title = config.get("title", "交易前提醒")
        self.root = tk.Tk()
        self.root.withdraw()
        self.windows = []
        self.entry = None
        self.status = None
        self.close_button = None
        self.done = False
        self._build()

    def _window_base(self, win, geometry):
        x, y, width, height = geometry
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.configure(bg="#070b10")
        win.attributes("-topmost", True)
        try:
            win.attributes("-fullscreen", True)
        except Exception:
            pass
        win.protocol("WM_DELETE_WINDOW", lambda: None)
        win.bind("<Escape>", lambda event: "break")
        win.bind("<Command-w>", lambda event: "break")
        win.bind("<Command-q>", lambda event: "break")
        win.bind("<Alt-F4>", lambda event: "break")
        win.bind("<<Paste>>", lambda event: "break")
        win.bind("<Command-v>", lambda event: "break")
        win.bind("<Control-v>", lambda event: "break")

    def _build_content(self, parent, primary):
        screen_width = parent.winfo_screenwidth()
        body_font = font.Font(family="PingFang SC", size=34, weight="bold")
        small_font = font.Font(family="PingFang SC", size=18)
        input_font = font.Font(family="PingFang SC", size=24)

        frame = tk.Frame(parent, bg="#070b10")
        frame.place(relx=0.5, rely=0.5, anchor="center", width=int(screen_width * 0.86))

        title = tk.Label(
            frame,
            text=self.title,
            bg="#070b10",
            fg="#9db4ff",
            font=small_font,
        )
        title.pack(pady=(0, 28))

        msg = tk.Label(
            frame,
            text=self.message,
            bg="#070b10",
            fg="#ffffff",
            font=body_font,
            wraplength=int(screen_width * 0.84),
            justify="center",
        )
        msg.pack(pady=(0, 34))

        hint = tk.Label(
            frame,
            text="请手动输入上面这句话，完全一致后才能关闭",
            bg="#070b10",
            fg="#9aa4b2",
            font=small_font,
        )
        hint.pack(pady=(0, 14))

        entry = tk.Text(
            frame,
            width=52,
            height=2,
            wrap="word",
            font=input_font,
            bg="#111827",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
            highlightthickness=2,
            highlightbackground="#2b3442",
            highlightcolor="#4f7cff",
        )
        entry.pack(ipady=14, pady=(0, 14))

        status = tk.Label(
            frame,
            text="",
            bg="#070b10",
            fg="#ff6b6b",
            font=small_font,
        )
        status.pack(pady=(0, 20))

        button = tk.Label(
            frame,
            text="确认关闭",
            font=small_font,
            bg="#245cff",
            fg="#ffffff",
            relief="flat",
            padx=36,
            pady=12,
            cursor="hand2",
        )
        button.pack()

        button.bind("<Button-1>", lambda event: self.try_close())
        button.bind("<Return>", lambda event: self.try_close())
        entry.bind("<Return>", self.handle_return)
        entry.bind("<KeyRelease>", lambda event: self.update_status())
        entry.bind("<<Paste>>", lambda event: "break")
        entry.bind("<Command-v>", lambda event: "break")
        entry.bind("<Control-v>", lambda event: "break")

        if primary:
            self.entry = entry
            self.status = status
            self.close_button = button
        else:
            entry.configure(state="disabled")
            button.configure(bg="#334155", fg="#94a3b8")

    def _build(self):
        self.root.deiconify()
        width = self.root.winfo_screenwidth()
        height = self.root.winfo_screenheight()
        geometry = (0, 0, width, height)
        self._window_base(self.root, geometry)
        self._build_content(self.root, True)
        self.windows.append(self.root)

    def input_text(self):
        if self.entry is None:
            return ""
        return self.entry.get("1.0", "end-1c").replace("\n", "")

    def first_mismatch(self, current):
        for index, expected_char in enumerate(self.message):
            if index >= len(current):
                return index, expected_char, ""
            if current[index] != expected_char:
                return index, expected_char, current[index]
        if len(current) > len(self.message):
            return len(self.message), "", current[len(self.message)]
        return None

    def handle_return(self, event):
        if self.input_text() == self.message:
            self.try_close()
        return "break"

    def update_status(self):
        if self.status is None or self.entry is None:
            return
        current = self.input_text()
        if current == self.message:
            self.status.configure(text="输入正确，可以关闭", fg="#3ddc97")
            if self.close_button is not None:
                self.close_button.configure(bg="#245cff", fg="#ffffff")
        else:
            mismatch = self.first_mismatch(current)
            if mismatch is None:
                text = "还不一致，请检查"
            else:
                index, expected_char, actual_char = mismatch
                if actual_char:
                    text = f"第 {index + 1} 个字不一致：应为「{expected_char}」，当前是「{actual_char}」"
                else:
                    text = f"还差第 {index + 1} 个字：应输入「{expected_char}」"
            self.status.configure(text=text, fg="#ff6b6b")
            if self.close_button is not None:
                self.close_button.configure(bg="#1d4ed8", fg="#ffffff")

    def try_close(self):
        if self.entry is None:
            return
        if self.input_text() == self.message:
            self.done = True
            self.root.after(10, self.close)
        else:
            self.update_status()
            self.entry.focus_force()
            self.root.bell()

    def close(self):
        for win in self.windows:
            try:
                win.destroy()
            except Exception:
                pass
        self.root.quit()

    def keep_front(self):
        if self.done:
            return
        activate_app()
        for win in self.windows:
            try:
                win.attributes("-topmost", True)
                win.lift()
            except Exception:
                pass
        if self.entry is not None:
            try:
                self.entry.focus_force()
            except Exception:
                pass
        seconds = float(self.config.get("keep_front_seconds", 3))
        self.root.after(max(1, int(seconds * 1000)), self.keep_front)

    def run(self):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        activate_app()
        self.root.after(250, self.keep_front)
        if self.entry is not None:
            self.entry.focus_force()
        self.root.mainloop()


def show_once(config):
    config = config.copy()
    config["message"] = daily_message(config)
    log("show reminder")
    app = ReminderOverlay(config)
    app.run()
    log("dismissed reminder")


def run_daemon():
    log("daemon started")
    while True:
        config = load_config()
        fire_at = next_fire_time(config)
        log(f"next reminder at {fire_at.isoformat()}")
        while True:
            now = dt.datetime.now(ZoneInfo(config.get("timezone", "Asia/Shanghai")))
            seconds = (fire_at - now).total_seconds()
            if seconds <= 0:
                break
            time.sleep(min(seconds, 60))
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--once"])
        log(f"reminder process exited with code {result.returncode}")
        time.sleep(float(config.get("snooze_seconds_after_success", 60)))


def main():
    parser = argparse.ArgumentParser(description="Daily full-screen trading discipline reminder.")
    parser.add_argument("--once", action="store_true", help="show the overlay immediately")
    parser.add_argument("--daemon", action="store_true", help="run forever and show at configured times")
    parser.add_argument("--print-next", action="store_true", help="print the next scheduled reminder time")
    parser.add_argument("--print-message", action="store_true", help="print today's selected message")
    args = parser.parse_args()

    config = load_config()
    if args.print_next:
        print(next_fire_time(config).isoformat())
        return
    if args.print_message:
        print(daily_message(config))
        return
    if args.once:
        show_once(config)
        return
    if args.daemon:
        run_daemon()
        return
    parser.print_help()


if __name__ == "__main__":
    main()
