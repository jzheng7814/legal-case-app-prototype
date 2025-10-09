#!/usr/bin/env python3
"""Simple Tkinter-based viewer for prettifying LLM log entries."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from typing import NamedTuple

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


REPO_ROOT = Path(__file__).resolve().parents[1]
LOGS_ROOT = REPO_ROOT / "backend" / "logs"


class LogPreset(NamedTuple):
    prefix: str
    label: str


LOG_PRESETS: Dict[str, LogPreset] = {
    "llm": LogPreset(prefix="llm", label="LLM"),
    "clearinghouse": LogPreset(prefix="clearinghouse", label="Clearinghouse"),
}
DEFAULT_ENTRY_LIMIT = 500
PAYLOAD_PRETTY_PRINT_THRESHOLD = 20_000


def discover_log_files(prefix: str) -> List[Path]:
    if not LOGS_ROOT.exists():
        return []
    candidates: List[Tuple[Path, float]] = []
    for path in LOGS_ROOT.glob(f"{prefix}-*.log"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((path, mtime))

    candidates.sort(key=lambda item: item[1], reverse=True)
    ordered = [path for path, _ in candidates]

    fallback = LOGS_ROOT / f"{prefix}.log"
    if fallback.exists() and fallback not in ordered:
        ordered.append(fallback)
    return ordered


def format_log_option(path: Path) -> str:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        stamp = mtime.strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError):
        stamp = "Unknown time"
    return f"{stamp} — {path.name}"


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
        self.direction = self._detect_direction()
        self.has_error = self._detect_error()
        self.summary = self._build_summary()

    def _build_summary(self) -> str:
        """Generate a concise summary string for list display."""
        prefix = f"{self.line_number}. "
        timestamp = self.timestamp or "Unknown time"
        level = self.level or "UNKNOWN"

        if not self.payload:
            return f"{prefix}{timestamp} [{level}] (unparsed)"

        special = _build_special_summary(self.payload)
        if special:
            return f"{prefix}{timestamp} [{level}] {special}"

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

    def _detect_direction(self) -> str:
        if not self.payload:
            return "unknown"

        if "request" in self.payload:
            return "outgoing"
        if "response" in self.payload:
            return "incoming"

        operation = _stringify(self.payload.get("operation")) or ""
        lowered = operation.lower()
        if lowered.endswith(".request") or ".request." in lowered:
            return "outgoing"
        if lowered.endswith(".request_error"):
            return "incoming"
        if lowered.endswith(".response") or lowered.endswith(".summary") or lowered.endswith(".error"):
            return "incoming"
        return "unknown"

    def _detect_error(self) -> bool:
        if self.error:
            return True
        if not self.payload:
            return False

        response = self.payload.get("response")
        if isinstance(response, dict):
            error_value = response.get("error")
            if error_value:
                return True

        direct_error = self.payload.get("error")
        if isinstance(direct_error, (dict, list)):
            return bool(direct_error)
        if direct_error:
            return True

        status = self.payload.get("status")
        if isinstance(status, str) and status.lower() in {"error", "failed", "failure"}:
            return True

        status_code = self.payload.get("status_code")
        if isinstance(status_code, int) and status_code >= 400:
            return True

        operation = _stringify(self.payload.get("operation")) or ""
        if operation.lower().endswith(".error"):
            return True

        return False


def _stringify(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def _build_special_summary(payload: Dict[str, Any]) -> Optional[str]:
    operation = _stringify(payload.get("operation"))
    if not operation:
        return None
    if operation.startswith("clearinghouse."):
        return _build_clearinghouse_summary(operation, payload)
    return None


def _build_clearinghouse_summary(operation: str, payload: Dict[str, Any]) -> str:
    short_op = operation.replace("clearinghouse.", "ch.")
    parts: List[str] = [short_op]

    params = payload.get("params")
    case_value = None
    if isinstance(params, dict):
        case_value = _stringify(params.get("case")) or _stringify(params.get("case_id"))

    path = _stringify(payload.get("path"))
    status = _stringify(payload.get("status_code"))
    payload_size = payload.get("payload_size")
    converted_count = payload.get("converted_count")
    result_count = payload.get("result_count")
    detail = _stringify(payload.get("detail"))
    if detail and len(detail) > 80:
        detail = f"{detail[:77]}..."

    if operation.endswith(".request"):
        if path:
            parts.append(path.strip())
        if case_value:
            parts.append(f"case={case_value}")
        timeout = payload.get("timeout_seconds")
        if timeout is not None:
            parts.append(f"timeout={timeout}s")
    elif operation.endswith(".response"):
        if status:
            parts.append(f"status={status}")
        if path:
            parts.append(path.strip())
        if isinstance(result_count, int):
            parts.append(f"results={result_count}")
        if isinstance(payload_size, int) and payload_size:
            parts.append(f"{payload_size} chars")
    elif operation.endswith(".http_error") or operation.endswith(".request_error"):
        if status:
            parts.append(f"status={status}")
        if case_value:
            parts.append(f"case={case_value}")
        if detail:
            parts.append(detail)
    elif operation.endswith("case_documents.summary"):
        case_id = _stringify(payload.get("case_id"))
        if case_id:
            parts.append(f"case={case_id}")
        if isinstance(converted_count, int):
            parts.append(f"converted={converted_count}")
        api_docs = payload.get("documents_api_count")
        api_dockets = payload.get("dockets_api_count")
        api_counts: List[str] = []
        if isinstance(api_docs, int):
            api_counts.append(f"docs={api_docs}")
        if isinstance(api_dockets, int):
            api_counts.append(f"dockets={api_dockets}")
        if api_counts:
            parts.append("api:" + ",".join(api_counts))
        case_title = _stringify(payload.get("case_title"))
        if case_title:
            parts.append(case_title)
    else:
        if path:
            parts.append(path.strip())
        if status:
            parts.append(f"status={status}")
        if case_value:
            parts.append(f"case={case_value}")

    filtered = [part for part in parts if part]
    return " | ".join(filtered)


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

    def __init__(
        self,
        log_path: Path,
        entry_limit: Optional[int] = None,
        *,
        log_label: str = "LLM",
        log_prefix: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.entry_limit = entry_limit
        self.log_label = log_label
        self.log_prefix = log_prefix
        self.entries: List[LogEntry] = []
        self._pending_selection: Optional[int] = None
        self._selection_job: Optional[str] = None
        self._is_loading = False
        self._pretty_print_limit = PAYLOAD_PRETTY_PRINT_THRESHOLD
        self._log_paths_by_label: Dict[str, Path] = {}
        self.log_selector_var = tk.StringVar()
        self.log_selector: Optional[ttk.Combobox] = None
        self._current_entry: Optional[LogEntry] = None
        self._full_payload_window: Optional[tk.Toplevel] = None
        self._full_payload_text: Optional[scrolledtext.ScrolledText] = None
        self._payload_truncated = False
        self.full_payload_button: Optional[ttk.Button] = None

        self.geometry("1120x640")

        self._set_log_path(log_path, update_selector=False)
        self._build_widgets()
        self.bind("<Down>", self._on_arrow_down)
        self.bind("<Up>", self._on_arrow_up)
        self._refresh_log_selector(initial=True)
        self._refresh_entries(initial_load=True)

    def _set_log_path(self, path: Path, *, update_selector: bool = True) -> None:
        resolved = path.resolve()
        self.log_path = resolved
        self.title(f"Log Viewer ({self.log_label}) - {self.log_path}")
        if update_selector and self.log_selector is not None:
            label = self._label_for_path(resolved)
            if label is not None:
                self.log_selector_var.set(label)

    def _label_for_path(self, path: Path) -> Optional[str]:
        for label, candidate in self._log_paths_by_label.items():
            if candidate == path:
                return label
        return None

    def _refresh_log_selector(self, *, initial: bool = False) -> None:
        if self.log_selector is None:
            return

        if self.log_prefix is None:
            label = format_log_option(self.log_path)
            self._log_paths_by_label = {label: self.log_path}
            self.log_selector.configure(values=[label], state="readonly")
            self.log_selector_var.set(label)
            self.log_selector.state(["disabled"])
            return

        candidates = discover_log_files(self.log_prefix)
        if not candidates:
            candidates = [self.log_path]
        else:
            if initial or not self.log_path.exists():
                self._set_log_path(candidates[0], update_selector=False)

        label_counts: Dict[str, int] = {}
        self._log_paths_by_label = {}
        values: List[str] = []
        for candidate in candidates:
            label = format_log_option(candidate)
            index = label_counts.get(label, 0)
            label_counts[label] = index + 1
            if index:
                label = f"{label} ({index + 1})"
            self._log_paths_by_label[label] = candidate
            values.append(label)

        current_label = self._label_for_path(self.log_path)
        if current_label is None:
            label = format_log_option(self.log_path)
            if label in self._log_paths_by_label:
                label = f"{label} ({self.log_path.name})"
            self._log_paths_by_label[label] = self.log_path
            values.insert(0, label)
            current_label = label

        self.log_selector.configure(values=values, state="readonly")
        self.log_selector_var.set(current_label or "")
        self.log_selector.state(["!disabled"])

    def _color_for_entry(self, entry: LogEntry) -> Optional[str]:
        if entry.direction == "outgoing":
            return "#1f6feb"
        if entry.direction == "incoming":
            return "#d73a49" if entry.has_error else "#2da44e"
        return None

    def _on_log_selected(self, _event: tk.Event) -> None:
        label = self.log_selector_var.get()
        new_path = self._log_paths_by_label.get(label)
        if new_path is None or new_path == self.log_path:
            return
        self._set_log_path(new_path, update_selector=False)
        self._refresh_entries(initial_load=True)

    def _on_arrow_down(self, _event: tk.Event) -> str:
        return self._move_selection(1)

    def _on_arrow_up(self, _event: tk.Event) -> str:
        return self._move_selection(-1)

    def _move_selection(self, delta: int) -> str:
        if not self.entries:
            return "break"
        selection = self.entry_listbox.curselection()
        if selection:
            index = selection[0] + delta
        else:
            index = 0 if delta > 0 else len(self.entries) - 1
        index = max(0, min(index, len(self.entries) - 1))
        self.entry_listbox.select_clear(0, tk.END)
        self.entry_listbox.select_set(index)
        self.entry_listbox.activate(index)
        self.entry_listbox.see(index)
        self.entry_listbox.event_generate("<<ListboxSelect>>")
        self.entry_listbox.focus_set()
        return "break"

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        toolbar.columnconfigure(2, weight=1)

        refresh_button = ttk.Button(toolbar, text="Refresh", command=self._refresh_entries)
        refresh_button.grid(row=0, column=0, padx=(0, 8))

        log_label = ttk.Label(toolbar, text=f"{self.log_label} log:")
        log_label.grid(row=0, column=1, sticky="w", padx=(0, 4))

        self.log_selector = ttk.Combobox(toolbar, state="readonly", textvariable=self.log_selector_var)
        self.log_selector.grid(row=0, column=2, sticky="ew")
        self.log_selector.bind("<<ComboboxSelected>>", self._on_log_selected)

        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(toolbar, textvariable=self.status_var)
        self.status_label.grid(row=0, column=3, sticky="e")

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

        payload_header = ttk.Frame(detail_frame)
        payload_header.grid(row=2, column=0, sticky="ew")
        payload_header.columnconfigure(0, weight=1)

        payload_label = ttk.Label(payload_header, text="Payload")
        payload_label.grid(row=0, column=0, sticky="w")

        self.full_payload_button = ttk.Button(
            payload_header,
            text="Open Full Payload",
            command=self._open_full_payload,
            state=tk.DISABLED,
        )
        self.full_payload_button.grid(row=0, column=1, sticky="e")

        self.payload_text = scrolledtext.ScrolledText(
            detail_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.payload_text.grid(row=3, column=0, sticky="nsew", pady=(2, 0))

        paned.add(detail_frame, weight=2)

    def _refresh_entries(self, initial_load: bool = False) -> None:
        if self.log_selector is not None:
            self._refresh_log_selector(initial=initial_load)

        self._set_busy(True, message="Refreshing log…")
        try:
            entries = load_log_entries(self.log_path, self.entry_limit)
        except FileNotFoundError:
            self._set_busy(False, message="Log file missing")
            messagebox.showerror("Log file not found", f"Could not find {self.log_path}")
            self._clear_details()
            self.entry_listbox.delete(0, tk.END)
            return

        previous_selection = self.entry_listbox.curselection()
        selected_index = previous_selection[0] if previous_selection else 0

        self._pending_selection = None
        self.entries = entries
        self.entry_listbox.delete(0, tk.END)
        for entry in entries:
            self.entry_listbox.insert(tk.END, entry.summary)
            color = self._color_for_entry(entry)
            if color:
                index = self.entry_listbox.size() - 1
                self.entry_listbox.itemconfig(index, foreground=color)

        if entries:
            safe_index = min(selected_index, len(entries) - 1)
            self.entry_listbox.select_set(safe_index)
            self.entry_listbox.event_generate("<<ListboxSelect>>")
        else:
            self._clear_details()

        self._set_busy(False)

        if initial_load and not entries:
            messagebox.showinfo("No log entries", f"{self.log_path} is currently empty.")

    def _on_entry_selected(self, event: tk.Event) -> None:  # type: ignore[override]
        selection = self.entry_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.entries):
            return
        self._pending_selection = index
        if self._selection_job is not None:
            self.after_cancel(self._selection_job)
        self._set_busy(True, message="Loading selection…")
        self._selection_job = self.after(10, self._render_pending_selection)

    def _render_pending_selection(self) -> None:
        self._selection_job = None
        index = self._pending_selection
        self._pending_selection = None
        if index is None or index >= len(self.entries):
            self._set_busy(False)
            return
        self._display_entry(self.entries[index])
        self._set_busy(False)

    def _set_busy(self, is_busy: bool, *, message: Optional[str] = None) -> None:
        if not hasattr(self, "status_var"):
            return
        if is_busy:
            self._is_loading = True
            self.status_var.set(message or "Loading…")
            self.configure(cursor="watch")
            self.update_idletasks()
        else:
            self._is_loading = False
            self.configure(cursor="")
            if message is not None:
                self.status_var.set(message)
            else:
                self._update_status()

    def _update_status(self) -> None:
        count = len(self.entries)
        if count:
            message = f"{count} entries"
            if self._payload_truncated and self._current_entry:
                message += " (preview truncated)"
            self.status_var.set(message)
        else:
            self.status_var.set("No entries")

    def _display_entry(self, entry: LogEntry) -> None:
        self._current_entry = entry
        metadata_lines = [
            f"Line: {entry.line_number}",
            f"Timestamp: {entry.timestamp or 'Unknown'}",
            f"Level: {entry.level or 'Unknown'}",
        ]

        if entry.payload:
            for key, value in entry.payload.items():
                if key in {"payload", "payload_preview"}:
                    continue
                if isinstance(value, (dict, list)):
                    continue
                metadata_lines.append(f"{key}: {value}")
            params = entry.payload.get("params")
            if isinstance(params, dict):
                for key, value in params.items():
                    metadata_lines.append(f"params.{key}: {value}")
        if entry.error:
            metadata_lines.append(f"Parse note: {entry.error}")

        metadata_content = "\n".join(metadata_lines)

        payload_content, truncated = self._format_payload(entry)
        payload_color = self._color_for_entry(entry)
        self._payload_truncated = truncated

        self._set_text(self.metadata_text, metadata_content)
        self._set_text(self.payload_text, payload_content, foreground=payload_color, tag="payload")
        self._update_full_payload_button()
        self._refresh_full_payload_window()

    def _clear_details(self) -> None:
        self._current_entry = None
        self._payload_truncated = False
        self._set_text(self.metadata_text, "")
        self._set_text(self.payload_text, "")
        self._update_full_payload_button()
        self._refresh_full_payload_window()

    def _format_payload(self, entry: LogEntry) -> Tuple[str, bool]:
        def build_preview(source: str) -> Tuple[str, bool]:
            if len(source) <= self._pretty_print_limit:
                return source, False
            preview = source[: self._pretty_print_limit]
            if not preview.endswith("…"):
                preview = f"{preview}…"
            note = (
                f"\n\n[Payload truncated to {self._pretty_print_limit:,} characters. "
                "Use \"Open Full Payload\" to view the rest.]"
            )
            return f"{preview}{note}", True

        if entry.payload is not None:
            if entry.json_text:
                preview, truncated = build_preview(entry.json_text)
                if truncated:
                    return preview, True
            try:
                return json.dumps(entry.payload, indent=2, ensure_ascii=False), False
            except (TypeError, ValueError):
                if entry.json_text:
                    return build_preview(entry.json_text)
        if entry.json_text:
            return build_preview(entry.json_text)
        return entry.raw_line, False

    @staticmethod
    def _set_text(
        widget: scrolledtext.ScrolledText,
        content: str,
        *,
        foreground: Optional[str] = None,
        tag: str = "content",
    ) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        if foreground:
            widget.tag_configure(tag, foreground=foreground)
            widget.insert(tk.END, content, tag)
        else:
            widget.insert(tk.END, content)
        widget.configure(state=tk.DISABLED)

    def _update_full_payload_button(self) -> None:
        if self.full_payload_button is None:
            return
        if self._current_entry and self._get_full_payload(self._current_entry):
            self.full_payload_button.state(["!disabled"])
        else:
            self.full_payload_button.state(["disabled"])

    def _open_full_payload(self) -> None:
        if not self._current_entry:
            return
        full_text = self._get_full_payload(self._current_entry)
        if full_text is None:
            return

        if (
            self._full_payload_window is not None
            and self._full_payload_window.winfo_exists()
            and self._full_payload_text is not None
        ):
            self._refresh_full_payload_window()
            self._full_payload_window.deiconify()
            self._full_payload_window.lift()
            return

        window = tk.Toplevel(self)
        window.title(f"Full Payload — {self.log_label} #{self._current_entry.line_number}")
        window.geometry("800x600")

        text_widget = scrolledtext.ScrolledText(window, wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True)

        color = self._color_for_entry(self._current_entry)
        if color:
            text_widget.tag_configure("payload", foreground=color)
            text_widget.insert(tk.END, full_text, "payload")
        else:
            text_widget.insert(tk.END, full_text)
        text_widget.configure(state=tk.DISABLED)

        window.protocol("WM_DELETE_WINDOW", self._close_full_payload_window)
        self._full_payload_window = window
        self._full_payload_text = text_widget

    def _refresh_full_payload_window(self) -> None:
        if self._full_payload_window is None or self._full_payload_text is None:
            return
        if not self._full_payload_window.winfo_exists():
            self._full_payload_window = None
            self._full_payload_text = None
            return

        if self._current_entry:
            full_text = self._get_full_payload(self._current_entry) or ""
            title = f"Full Payload — {self.log_label} #{self._current_entry.line_number}"
            color = self._color_for_entry(self._current_entry)
        else:
            full_text = ""
            title = "Full Payload"
            color = None

        self._full_payload_text.configure(state=tk.NORMAL)
        self._full_payload_text.delete("1.0", tk.END)
        if color:
            self._full_payload_text.tag_configure("payload", foreground=color)
            self._full_payload_text.insert(tk.END, full_text, "payload")
        else:
            self._full_payload_text.insert(tk.END, full_text)
        self._full_payload_text.configure(state=tk.DISABLED)
        self._full_payload_window.title(title)

    def _close_full_payload_window(self) -> None:
        if self._full_payload_window is not None and self._full_payload_window.winfo_exists():
            self._full_payload_window.destroy()
        self._full_payload_window = None
        self._full_payload_text = None

    @staticmethod
    def _get_full_payload(entry: LogEntry) -> Optional[str]:
        if entry.payload is not None:
            try:
                return json.dumps(entry.payload, indent=2, ensure_ascii=False)
            except (TypeError, ValueError):
                if entry.json_text:
                    return entry.json_text
                return str(entry.payload)
        if entry.json_text:
            return entry.json_text
        return entry.raw_line


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="View formatted LLM log entries in a Tkinter UI.")
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Path to the log file (default: use --log-type preset)",
    )
    parser.add_argument(
        "--log-type",
        choices=sorted(LOG_PRESETS.keys()),
        default="llm",
        help="Select a predefined log to open when --log is not provided.",
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
    if args.log is not None:
        selected_path = args.log
        log_label = "Custom"
        log_prefix = None
    else:
        preset = LOG_PRESETS[args.log_type]
        candidates = discover_log_files(preset.prefix)
        if candidates:
            selected_path = candidates[0]
        else:
            selected_path = LOGS_ROOT / f"{preset.prefix}.log"
        log_label = preset.label
        log_prefix = preset.prefix
    log_path = resolve_log_path(selected_path)
    entry_limit = args.limit if args.limit and args.limit > 0 else None

    app = LLMLogViewer(
        log_path=log_path,
        entry_limit=entry_limit,
        log_label=log_label,
        log_prefix=log_prefix,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
