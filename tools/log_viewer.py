#!/usr/bin/env python3
"""Tkinter log viewer for Event system logs (file or live UDS stream)."""

from __future__ import annotations

import json
import queue
import socket
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOCKET_PATH = "/tmp/gavel_tool.sock"
APP_CONFIG_PATH = REPO_ROOT / "backend" / "config" / "app.config.json"


@dataclass
class LogEntry:
    timestamp: str
    level: str
    producer: str
    description: str
    payload: Optional[Dict[str, Any]] = None
    raw_line: Optional[str] = None


def _load_socket_path() -> str:
    try:
        raw = json.loads(APP_CONFIG_PATH.read_text(encoding="utf-8"))
        app_config = raw.get("app") or {}
        path = app_config.get("ipc_socket_path")
        if isinstance(path, str) and path.strip():
            return path.strip()
    except (OSError, ValueError, json.JSONDecodeError):
        return DEFAULT_SOCKET_PATH
    return DEFAULT_SOCKET_PATH


def _parse_log_line(line: str) -> Optional[LogEntry]:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return LogEntry(
            timestamp="",
            level="",
            producer="",
            description="Unparseable JSON log line",
            payload={"raw": stripped},
            raw_line=stripped,
        )
    timestamp = str(payload.get("timestamp") or "")
    return LogEntry(
        timestamp=_format_timestamp(timestamp),
        level=str(payload.get("visibility") or ""),
        producer=str(payload.get("producer") or ""),
        description=str(payload.get("description") or ""),
        payload=payload.get("payload") if isinstance(payload, dict) else None,
        raw_line=stripped,
    )


def _format_timestamp(value: str) -> str:
    if not value:
        return ""
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone()
    ms = int(round(local.microsecond / 1000))
    if ms >= 1000:
        local = local.replace(microsecond=0) + timedelta(seconds=1)
        ms = 0
    return local.strftime("%m-%d-%y %H:%M:%S.") + f"{ms:03d}"


def _check_socket_connection(socket_path: str) -> bool:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        sock.connect(socket_path)
        sock.close()
        return True
    except OSError:
        return False


class LiveLogStream:
    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.queue: queue.Queue[LogEntry] = queue.Queue()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self._socket_path)
        except OSError as exc:
            self.queue.put(
                LogEntry(
                    timestamp="",
                    level="ERROR",
                    producer="log_viewer",
                    description=f"Failed to connect to socket: {exc}",
                    payload=None,
                )
            )
            return

        buffer = ""
        with sock:
            while not self._stop_event.is_set():
                try:
                    data = sock.recv(4096)
                except OSError:
                    break
                if not data:
                    break
                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    entry = _parse_log_line(line)
                    if entry:
                        self.queue.put(entry)


class LogViewerWindow(tk.Toplevel):
    def __init__(self, master: tk.Tk, *, title: str, live_stream: Optional[LiveLogStream] = None) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry("1100x680")
        self._entries: list[LogEntry] = []
        self._payload_cache: Dict[int, str] = {}
        self._auto_scroll = True
        self._live_stream = live_stream
        self._poll_job: Optional[str] = None
        self._on_close_callback: Optional[callable] = None

        self._build_ui()
        self._configure_tags()

        if self._live_stream:
            self._start_live_poll()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def set_close_callback(self, callback: Optional[callable]) -> None:
        self._on_close_callback = callback

    def load_file(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            messagebox.showerror("Log file error", f"Failed to read {path}:\n{exc}")
            return

        self._entries = []
        self._payload_cache = {}
        self.tree.delete(*self.tree.get_children())
        for line in lines:
            entry = _parse_log_line(line)
            if entry:
                self._append_entry(entry)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        paned = ttk.Panedwindow(self, orient=tk.VERTICAL)
        paned.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Top pane: log list
        top_frame = ttk.Frame(paned)
        top_frame.columnconfigure(0, weight=1)
        top_frame.rowconfigure(0, weight=1)

        columns = ("timestamp", "level", "producer", "description")
        self.tree = ttk.Treeview(
            top_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.heading("level", text="Level")
        self.tree.heading("producer", text="Producer")
        self.tree.heading("description", text="Message")
        self.tree.column("timestamp", width=200, stretch=False)
        self.tree.column("level", width=90, stretch=False, anchor="center")
        self.tree.column("producer", width=220, stretch=False)
        self.tree.column("description", width=520, stretch=True)

        yscroll = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self._on_scrollbar)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<MouseWheel>", self._on_mousewheel)
        self.tree.bind("<Button-4>", self._on_mousewheel)
        self.tree.bind("<Button-5>", self._on_mousewheel)

        paned.add(top_frame, weight=3)

        # Bottom pane: payload
        bottom_frame = ttk.Frame(paned)
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.rowconfigure(1, weight=1)

        payload_label = ttk.Label(bottom_frame, text="Payload")
        payload_label.grid(row=0, column=0, sticky="w")

        self.payload_text = scrolledtext.ScrolledText(bottom_frame, wrap=tk.WORD, state=tk.DISABLED, height=12)
        self.payload_text.grid(row=1, column=0, sticky="nsew")

        paned.add(bottom_frame, weight=1)

    def _configure_tags(self) -> None:
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=24)
        style.configure("Treeview", background="#2f2f2f", foreground="#e6e6e6", fieldbackground="#2f2f2f")

        self.tree.tag_configure("row_even", background="#2f2f2f")
        self.tree.tag_configure("row_odd", background="#3a3a3a")
        self.tree.tag_configure("level_warning", foreground="#b58900")
        self.tree.tag_configure("level_error", foreground="#dc322f")

    def _append_entry(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        index = len(self._entries) - 1
        row_tag = "row_even" if index % 2 == 0 else "row_odd"
        tags = [row_tag]
        level = entry.level.upper()
        if level == "WARNING":
            tags.append("level_warning")
        elif level == "ERROR":
            tags.append("level_error")
        self.tree.insert(
            "",
            tk.END,
            iid=str(index),
            values=(entry.timestamp, entry.level, entry.producer, entry.description),
            tags=tuple(tags),
        )
        if self._auto_scroll:
            self.tree.yview_moveto(1.0)

    def _on_select(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        index = int(selection[0])
        if index >= len(self._entries):
            return
        cached = self._payload_cache.get(index)
        if cached is None:
            entry = self._entries[index]
            payload = entry.payload
            content = ""
            if payload is not None:
                try:
                    content = json.dumps(payload, indent=2, ensure_ascii=False)
                except (TypeError, ValueError):
                    content = str(payload)
            self._payload_cache[index] = content
            cached = content
        self._set_payload_text(cached)

    def _set_payload_text(self, content: str) -> None:
        self.payload_text.configure(state=tk.NORMAL)
        self.payload_text.delete("1.0", tk.END)
        self.payload_text.insert(tk.END, content)
        self.payload_text.configure(state=tk.DISABLED)

    def _on_mousewheel(self, _event: tk.Event) -> None:
        self._update_auto_scroll()

    def _on_scrollbar(self, *args: Any) -> None:
        self.tree.yview(*args)
        self._update_auto_scroll()

    def _update_auto_scroll(self) -> None:
        _, end = self.tree.yview()
        self._auto_scroll = end >= 0.999

    def _start_live_poll(self) -> None:
        if not self._live_stream:
            return
        self._live_stream.start()
        self._poll_job = self.after(100, self._poll_live_queue)

    def _poll_live_queue(self) -> None:
        if not self._live_stream:
            return
        max_per_tick = 200
        processed = 0
        while processed < max_per_tick:
            try:
                entry = self._live_stream.queue.get_nowait()
            except queue.Empty:
                break
            self._append_entry(entry)
            processed += 1
        delay = 10 if processed >= max_per_tick else 100
        self._poll_job = self.after(delay, self._poll_live_queue)

    def _on_close(self) -> None:
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
        if self._live_stream:
            self._live_stream.stop()
        if self._on_close_callback:
            self._on_close_callback()
        self.destroy()


class LogViewerLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Log Viewer")
        self.geometry("420x180")
        self.resizable(False, False)

        self._live_window: Optional[LogViewerWindow] = None
        self._live_stream: Optional[LiveLogStream] = None

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        label = ttk.Label(frame, text="Open log viewer")
        label.pack(anchor="w", pady=(0, 12))

        self.file_button = ttk.Button(
            frame,
            text="Open Viewer From File",
            command=self._open_file_viewer,
        )
        self.file_button.pack(fill=tk.X, pady=(0, 8))

        self.live_button = ttk.Button(
            frame,
            text="Listen to Live Log Stream",
            command=self._open_live_viewer,
        )
        self.live_button.pack(fill=tk.X)

    def _open_file_viewer(self) -> None:
        path = filedialog.askopenfilename(
            title="Select log file",
            filetypes=[("Log files", "*.log"), ("All files", "*.*")],
        )
        if not path:
            return
        log_path = Path(path)
        viewer = LogViewerWindow(self, title=f"Log Viewer — {log_path.name}")
        viewer.load_file(log_path)

    def _open_live_viewer(self) -> None:
        if self._live_window and self._live_window.winfo_exists():
            return

        socket_path = _load_socket_path()
        if not _check_socket_connection(socket_path):
            messagebox.showerror(
                "Connection error",
                f"Unable to connect to log socket at {socket_path}",
            )
            return

        stream = LiveLogStream(socket_path)
        viewer = LogViewerWindow(self, title="Live Log Viewer", live_stream=stream)

        def _on_close() -> None:
            self._live_window = None
            self._live_stream = None
            self.live_button.state(["!disabled"])

        viewer.set_close_callback(_on_close)
        self._live_window = viewer
        self._live_stream = stream
        self.live_button.state(["disabled"])


def main() -> None:
    app = LogViewerLauncher()
    app.mainloop()


if __name__ == "__main__":
    main()
