#!/usr/bin/env python3
"""Simple Tkinter-based viewer for prettifying LLM log entries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = REPO_ROOT / "backend" / "logs" / "llm.log"
DEFAULT_ENTRY_LIMIT = 500


class LogEntry:
    """Container for a parsed log line."""

    def __init__(
        self,
        *,
        line_number: int,
        raw_line: str,
        timestamp: str,
        level: str,
        payload: Optional[Dict[str, Any]],
        json_text: Optional[str],
        error: Optional[str],
    ) -> None:
        self.line_number = line_number
        self.raw_line = raw_line
        self.timestamp = timestamp
        self.level = level
        self.payload = payload
        self.json_text = json_text
        self.error = error
        self.summary = self._build_summary()

    def _build_summary(self) -> str:
        """Generate a concise summary string for list display."""
        prefix = f"{self.line_number}. "
        timestamp = self.timestamp or "Unknown time"
        level = self.level or "UNKNOWN"

        if not self.payload:
            return f"{prefix}{timestamp} [{level}] (unparsed)"

        # Prefer human-friendly details when available.
        operation = _stringify(self.payload.get("operation"))
        model = _stringify(self.payload.get("model"))
        status = _stringify(self.payload.get("status"))

        detail_parts = [p for p in (operation, model or status) if p]

        if not detail_parts:
            detail_parts = [_stringify(self.payload.get("event")), _stringify(self.payload.get("phase"))]
            detail_parts = [p for p in detail_parts if p]

        if detail_parts:
            details = " | ".join(detail_parts)
            return f"{prefix}{timestamp} [{level}] {details}"

        return f"{prefix}{timestamp} [{level}]"


def _stringify(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def parse_log_line(raw_line: str, line_number: int) -> LogEntry:
    """Parse a single log line into a LogEntry."""
    stripped = raw_line.strip()
    idx = stripped.find("{")
    timestamp = ""
    level = ""
    payload: Optional[Dict[str, Any]] = None
    json_text: Optional[str] = None
    error: Optional[str] = None

    if idx != -1:
        prefix = stripped[:idx].strip()
        json_text = stripped[idx:]
        parts = prefix.split()
        if len(parts) >= 2:
            timestamp = " ".join(parts[:2])
        if len(parts) >= 3:
            level = parts[2]
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError as exc:
            error = f"JSON decode error: {exc}"
    else:
        error = "No JSON payload found"

    return LogEntry(
        line_number=line_number,
        raw_line=raw_line.rstrip("\n"),
        timestamp=timestamp,
        level=level,
        payload=payload,
        json_text=json_text,
        error=error,
    )


def load_log_entries(log_path: Path, limit: Optional[int] = None) -> List[LogEntry]:
    """Load and parse log entries from the log file."""
    if not log_path.exists():
        raise FileNotFoundError(log_path)

    with log_path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()

    if limit and limit > 0:
        lines_to_parse = lines[-limit:]
        start_line_number = len(lines) - len(lines_to_parse) + 1
    else:
        lines_to_parse = lines
        start_line_number = 1

    entries = [
        parse_log_line(raw_line, line_number)
        for line_number, raw_line in enumerate(lines_to_parse, start=start_line_number)
    ]
    return entries


class LLMLogViewer(tk.Tk):
    """Main Tkinter application window."""

    def __init__(self, log_path: Path, entry_limit: Optional[int] = None) -> None:
        super().__init__()
        self.log_path = log_path
        self.entry_limit = entry_limit
        self.entries: List[LogEntry] = []

        self.title(f"LLM Log Viewer - {self.log_path}")
        self.geometry("1120x640")

        self._build_widgets()
        self._refresh_entries(initial_load=True)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        toolbar.columnconfigure(1, weight=1)

        refresh_button = ttk.Button(toolbar, text="Refresh", command=self._refresh_entries)
        refresh_button.grid(row=0, column=0, padx=(0, 8))

        self.path_label = ttk.Label(toolbar, text=str(self.log_path))
        self.path_label.grid(row=0, column=1, sticky="w")

        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        # Left: list of log entries
        list_frame = ttk.Frame(paned)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.entry_listbox = tk.Listbox(
            list_frame,
            activestyle="dotbox",
            selectmode=tk.SINGLE,
            exportselection=False,
        )
        self.entry_listbox.grid(row=0, column=0, sticky="nsew")

        list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.entry_listbox.yview)
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.entry_listbox.configure(yscrollcommand=list_scrollbar.set)

        self.entry_listbox.bind("<<ListboxSelect>>", self._on_entry_selected)

        paned.add(list_frame, weight=1)

        # Right: details pane
        detail_frame = ttk.Frame(paned)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(2, weight=1)

        metadata_label = ttk.Label(detail_frame, text="Metadata")
        metadata_label.grid(row=0, column=0, sticky="w")

        self.metadata_text = scrolledtext.ScrolledText(
            detail_frame,
            wrap=tk.WORD,
            height=8,
            state=tk.DISABLED,
        )
        self.metadata_text.grid(row=1, column=0, sticky="nsew", pady=(2, 8))

        payload_label = ttk.Label(detail_frame, text="Payload")
        payload_label.grid(row=2, column=0, sticky="w")

        self.payload_text = scrolledtext.ScrolledText(
            detail_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.payload_text.grid(row=3, column=0, sticky="nsew", pady=(2, 0))

        paned.add(detail_frame, weight=2)

    def _refresh_entries(self, initial_load: bool = False) -> None:
        try:
            entries = load_log_entries(self.log_path, self.entry_limit)
        except FileNotFoundError:
            messagebox.showerror("Log file not found", f"Could not find {self.log_path}")
            self._clear_details()
            self.entry_listbox.delete(0, tk.END)
            return

        previous_selection = self.entry_listbox.curselection()
        selected_index = previous_selection[0] if previous_selection else 0

        self.entries = entries
        self.entry_listbox.delete(0, tk.END)
        for entry in entries:
            self.entry_listbox.insert(tk.END, entry.summary)

        if entries:
            safe_index = min(selected_index, len(entries) - 1)
            self.entry_listbox.select_set(safe_index)
            self.entry_listbox.event_generate("<<ListboxSelect>>")
        else:
            self._clear_details()

        if initial_load and not entries:
            messagebox.showinfo("No log entries", f"{self.log_path} is currently empty.")

    def _on_entry_selected(self, event: tk.Event) -> None:  # type: ignore[override]
        selection = self.entry_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.entries):
            return
        self._display_entry(self.entries[index])

    def _display_entry(self, entry: LogEntry) -> None:
        metadata_lines = [
            f"Line: {entry.line_number}",
            f"Timestamp: {entry.timestamp or 'Unknown'}",
            f"Level: {entry.level or 'Unknown'}",
        ]

        if entry.payload:
            for key, value in entry.payload.items():
                if isinstance(value, (dict, list)):
                    continue
                metadata_lines.append(f"{key}: {value}")
        if entry.error:
            metadata_lines.append(f"Parse note: {entry.error}")

        metadata_content = "\n".join(metadata_lines)

        payload_content = ""
        if entry.payload is not None:
            payload_content = json.dumps(entry.payload, indent=2, ensure_ascii=False)
        elif entry.json_text:
            payload_content = entry.json_text
        else:
            payload_content = entry.raw_line

        self._set_text(self.metadata_text, metadata_content)
        self._set_text(self.payload_text, payload_content)

    def _clear_details(self) -> None:
        self._set_text(self.metadata_text, "")
        self._set_text(self.payload_text, "")

    @staticmethod
    def _set_text(widget: scrolledtext.ScrolledText, content: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, content)
        widget.configure(state=tk.DISABLED)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="View formatted LLM log entries in a Tkinter UI.")
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help=f"Path to the log file (default: {DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_ENTRY_LIMIT,
        help="Maximum number of recent entries to load (default: %(default)s, set to 0 for all)",
    )
    return parser.parse_args()


def resolve_log_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def main() -> None:
    args = parse_args()
    log_path = resolve_log_path(args.log)
    entry_limit = args.limit if args.limit and args.limit > 0 else None

    app = LLMLogViewer(log_path=log_path, entry_limit=entry_limit)
    app.mainloop()


if __name__ == "__main__":
    main()
