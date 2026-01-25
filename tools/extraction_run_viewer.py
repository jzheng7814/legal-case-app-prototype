#!/usr/bin/env python3
"""Live viewer for extraction runs based on Event system logs."""

from __future__ import annotations

import json
import queue
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_CONFIG_PATH = REPO_ROOT / "backend" / "config" / "app.config.json"
DEFAULT_SOCKET_PATH = "/tmp/gavel_tool.sock"


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


def _check_socket_connection(socket_path: str) -> bool:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        sock.connect(socket_path)
        sock.close()
        return True
    except OSError:
        return False


@dataclass
class EventRecord:
    timestamp: str
    visibility: str
    producer: str
    description: str
    payload: Dict[str, Any]
    case_id: Optional[str] = None


@dataclass
class LlmEvent:
    kind: str  # request | response
    turn: int
    timestamp: str
    payload: Dict[str, Any]


@dataclass
class ChecklistItem:
    value: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RunState:
    case_id: str
    status: str = "running"
    steps: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    llm_turn_counter: int = 0
    pending_turn: Optional[int] = None
    llm_events: List[LlmEvent] = field(default_factory=list)
    checklist: Dict[str, List[ChecklistItem]] = field(default_factory=dict)


def _parse_event_line(line: str) -> Optional[EventRecord]:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return EventRecord(
        timestamp=str(payload.get("timestamp") or ""),
        visibility=str(payload.get("visibility") or ""),
        producer=str(payload.get("producer") or ""),
        description=str(payload.get("description") or ""),
        payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
        case_id=str(payload.get("case_id")) if payload.get("case_id") is not None else None,
    )


class LiveLogStream:
    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.queue: queue.Queue[EventRecord] = queue.Queue()

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
                EventRecord(
                    timestamp="",
                    visibility="ERROR",
                    producer="extraction_run_viewer",
                    description=f"Failed to connect to socket: {exc}",
                    payload={},
                    case_id=None,
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
                    record = _parse_event_line(line)
                    if record:
                        self.queue.put(record)


class ExtractionRunViewer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Extraction Run Monitor")
        self.geometry("1200x720")

        socket_path = _load_socket_path()
        if not _check_socket_connection(socket_path):
            messagebox.showerror(
                "Connection error",
                f"Unable to connect to log socket at {socket_path}",
            )
            self.destroy()
            return

        self._stream = LiveLogStream(socket_path)
        self._stream.start()
        self._poll_job: Optional[str] = None

        self._runs: Dict[str, RunState] = {}
        self._run_order: List[str] = []
        self._selected_case_id: Optional[str] = None

        self._mode = tk.StringVar(value="agent")
        self._mode_value = tk.DoubleVar(value=0.0)
        self._auto_scroll_llm = True

        self._build_ui()
        self._poll_job = self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Left: run list
        left_frame = ttk.Frame(paned)
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)

        ttk.Label(left_frame, text="Runs").grid(row=0, column=0, sticky="w")
        self.run_list = tk.Listbox(left_frame, exportselection=False)
        self.run_list.grid(row=1, column=0, sticky="nsew")
        self.run_list.bind("<<ListboxSelect>>", self._on_run_selected)
        run_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.run_list.yview)
        run_scroll.grid(row=1, column=1, sticky="ns")
        self.run_list.configure(yscrollcommand=run_scroll.set)

        paned.add(left_frame, weight=1)

        # Right: mode + content
        right_frame = ttk.Frame(paned)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        mode_frame = ttk.Frame(right_frame)
        mode_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        mode_frame.columnconfigure(0, weight=1)

        ttk.Label(mode_frame, text="View").grid(row=0, column=0, sticky="w")
        ttk.Label(mode_frame, text="Agent").grid(row=0, column=1, padx=(10, 4))
        slider = ttk.Scale(
            mode_frame,
            from_=0.0,
            to=1.0,
            orient=tk.HORIZONTAL,
            variable=self._mode_value,
            command=self._on_mode_slide,
            length=140,
        )
        slider.grid(row=0, column=2)
        ttk.Label(mode_frame, text="Checklist").grid(row=0, column=3, padx=(4, 0))

        self.agent_pane = ttk.Panedwindow(right_frame, orient=tk.HORIZONTAL)
        self.agent_pane.grid(row=1, column=0, sticky="nsew")

        llm_list_frame = ttk.Frame(self.agent_pane)
        llm_list_frame.columnconfigure(0, weight=1)
        llm_list_frame.rowconfigure(0, weight=1)
        self.llm_list = tk.Listbox(llm_list_frame, exportselection=False)
        self.llm_list.grid(row=0, column=0, sticky="nsew")
        self.llm_list.bind("<<ListboxSelect>>", self._on_llm_selected)
        self.llm_list.bind("<MouseWheel>", self._on_llm_scroll)
        self.llm_list.bind("<Button-4>", self._on_llm_scroll)
        self.llm_list.bind("<Button-5>", self._on_llm_scroll)
        llm_scroll = ttk.Scrollbar(llm_list_frame, orient=tk.VERTICAL, command=self.llm_list.yview)
        llm_scroll.grid(row=0, column=1, sticky="ns")
        self.llm_list.configure(yscrollcommand=llm_scroll.set)

        llm_detail_frame = ttk.Frame(self.agent_pane)
        llm_detail_frame.columnconfigure(0, weight=1)
        llm_detail_frame.rowconfigure(0, weight=1)
        self.llm_detail = scrolledtext.ScrolledText(llm_detail_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.llm_detail.grid(row=0, column=0, sticky="nsew")

        self.agent_pane.add(llm_list_frame, weight=1)
        self.agent_pane.add(llm_detail_frame, weight=3)

        self.checklist_frame = ttk.Frame(right_frame)
        self.checklist_frame.grid(row=1, column=0, sticky="nsew")
        self.checklist_frame.columnconfigure(0, weight=1)
        self.checklist_frame.rowconfigure(0, weight=1)
        self.checklist_text = scrolledtext.ScrolledText(
            self.checklist_frame, wrap=tk.WORD, state=tk.DISABLED
        )
        self.checklist_text.grid(row=0, column=0, sticky="nsew")

        paned.add(right_frame, weight=3)
        self._refresh_right_pane()

    def _refresh_right_pane(self) -> None:
        if self._mode.get() == "agent":
            self.checklist_frame.grid_remove()
            self.agent_pane.grid()
            self._refresh_agent_view()
        else:
            self.agent_pane.grid_remove()
            self.checklist_frame.grid()
            self._refresh_checklist_view()

    def _on_mode_slide(self, _value: str) -> None:
        mode = "agent" if self._mode_value.get() < 0.5 else "checklist"
        if mode != self._mode.get():
            self._mode.set(mode)
            self._refresh_right_pane()

    def _on_run_selected(self, _event: tk.Event) -> None:
        selection = self.run_list.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self._run_order):
            return
        self._selected_case_id = self._run_order[idx]
        self._refresh_right_pane()

    def _on_llm_selected(self, _event: tk.Event) -> None:
        selection = self.llm_list.curselection()
        if not selection:
            return
        idx = selection[0]
        run = self._get_selected_run()
        if not run or idx >= len(run.llm_events):
            return
        event = run.llm_events[idx]
        self._set_text(self.llm_detail, self._format_llm_event(event))

    def _on_llm_scroll(self, _event: tk.Event) -> None:
        self._update_llm_autoscroll()

    def _update_llm_autoscroll(self) -> None:
        _, end = self.llm_list.yview()
        self._auto_scroll_llm = end >= 0.999

    def _poll_events(self) -> None:
        max_per_tick = 400
        processed = 0
        while processed < max_per_tick:
            try:
                record = self._stream.queue.get_nowait()
            except queue.Empty:
                break
            self._handle_event(record)
            processed += 1
        delay = 50 if processed >= max_per_tick else 150
        self._poll_job = self.after(delay, self._poll_events)

    def _handle_event(self, record: EventRecord) -> None:
        if not record.case_id:
            return

        run = self._runs.get(record.case_id)
        if run is None:
            run = RunState(case_id=record.case_id)
            self._runs[record.case_id] = run
            self._run_order.append(record.case_id)
            self._refresh_run_list()

        if record.producer.endswith("agent.driver"):
            if record.description == "Starting agent extraction":
                run.status = "running"
                run.started_at = record.timestamp
            elif record.description == "Agent step":
                step = record.payload.get("step")
                if isinstance(step, int):
                    run.steps = max(run.steps, step)
            elif record.description == "Agent run complete":
                run.status = "completed"
                run.completed_at = record.timestamp

        if record.producer.endswith("services.llm"):
            if record.description == "LLM request record":
                run.llm_turn_counter += 1
                run.pending_turn = run.llm_turn_counter
                run.llm_events.append(
                    LlmEvent(
                        kind="request",
                        turn=run.llm_turn_counter,
                        timestamp=record.timestamp,
                        payload=record.payload,
                    )
                )
            elif record.description == "LLM response record":
                turn = run.pending_turn or (run.llm_turn_counter + 1)
                run.llm_events.append(
                    LlmEvent(
                        kind="response",
                        turn=turn,
                        timestamp=record.timestamp,
                        payload=record.payload,
                    )
                )
                run.pending_turn = None

        if record.description == "Checklist updated":
            action = record.payload.get("action")
            key = record.payload.get("key")
            items = record.payload.get("items", [])
            if isinstance(key, str) and isinstance(items, list):
                converted = [self._convert_checklist_item(item) for item in items if isinstance(item, dict)]
                if action == "update":
                    run.checklist[key] = converted
                elif action == "append":
                    current = run.checklist.get(key, [])
                    current.extend(converted)
                    run.checklist[key] = current

        if record.case_id == self._selected_case_id:
            if self._mode.get() == "agent":
                self._refresh_agent_view()
            else:
                self._refresh_checklist_view()
        self._refresh_run_list()

    def _refresh_run_list(self) -> None:
        self.run_list.delete(0, tk.END)
        for case_id in self._run_order:
            run = self._runs[case_id]
            status = run.status
            step_part = f" step {run.steps}" if run.steps else ""
            self.run_list.insert(tk.END, f"{case_id} — {status}{step_part}")
        if self._selected_case_id in self._run_order:
            idx = self._run_order.index(self._selected_case_id)
            self.run_list.select_set(idx)

    def _refresh_agent_view(self) -> None:
        run = self._get_selected_run()
        self.llm_list.delete(0, tk.END)
        if not run:
            self._set_text(self.llm_detail, "")
            return

        for event in run.llm_events:
            label = f"T{event.turn} {event.kind.capitalize()} — {event.timestamp}"
            self.llm_list.insert(tk.END, label)
        if run.llm_events:
            if self._auto_scroll_llm:
                self.llm_list.yview_moveto(1.0)
            self.llm_list.select_set(len(run.llm_events) - 1)
            self.llm_list.event_generate("<<ListboxSelect>>")
        else:
            self._set_text(self.llm_detail, "")

    def _refresh_checklist_view(self) -> None:
        run = self._get_selected_run()
        if not run:
            self._set_text(self.checklist_text, "")
            return
        lines: List[str] = []
        for key in sorted(run.checklist.keys()):
            entries = run.checklist[key]
            lines.append(f"{key} ({len(entries)} values)")
            for idx, item in enumerate(entries, 1):
                lines.append(f"  {idx}. {item.value}")
                for ev_idx, ev in enumerate(item.evidence, 1):
                    text = ev.get("text") or ""
                    doc = ev.get("source_document") or ev.get("document_id") or "unknown"
                    loc = ev.get("location") or "unknown"
                    snippet = text.strip().replace("\n", " ")
                    if len(snippet) > 160:
                        snippet = snippet[:157] + "..."
                    lines.append(f"     Evidence {ev_idx}: [{doc}] {loc}")
                    if snippet:
                        lines.append(f"       \"{snippet}\"")
            lines.append("")
        self._set_text(self.checklist_text, "\n".join(lines).strip())

    def _format_llm_event(self, event: LlmEvent) -> str:
        lines: List[str] = [f"Turn {event.turn} {event.kind.upper()} — {event.timestamp}"]
        payload = event.payload

        if event.kind == "request":
            system = payload.get("system")
            request = payload.get("request", {})
            messages = request.get("messages", [])
            if system:
                lines.append("\n[System]\n" + str(system).strip())
            if messages:
                lines.append("\n[Messages]")
                for msg in messages:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    lines.append(f"\n{role.upper()}:\n{str(content).strip()}")
        else:
            response = payload.get("response", {})
            message = response.get("message", {})
            thinking = message.get("thinking")
            content = message.get("content")
            tool_calls = message.get("tool_calls") or []

            if thinking:
                lines.append("\n[Thinking]\n" + str(thinking).strip())
            if content:
                lines.append("\n[Content]\n" + str(content).strip())
            if tool_calls:
                lines.append("\n[Tool Calls]")
                for call in tool_calls:
                    function = call.get("function") or {}
                    name = function.get("name", "unknown")
                    args = function.get("arguments", {})
                    lines.append(f"- {name}")
                    try:
                        lines.append(json.dumps(args, indent=2, ensure_ascii=False))
                    except (TypeError, ValueError):
                        lines.append(str(args))
        return "\n".join(lines).strip()

    @staticmethod
    def _convert_checklist_item(item: Dict[str, Any]) -> ChecklistItem:
        value = str(item.get("value") or "")
        evidence = item.get("evidence") or []
        if isinstance(evidence, dict):
            evidence_list = [evidence]
        elif isinstance(evidence, list):
            evidence_list = evidence
        else:
            evidence_list = []
        return ChecklistItem(value=value, evidence=[e for e in evidence_list if isinstance(e, dict)])

    def _get_selected_run(self) -> Optional[RunState]:
        if not self._selected_case_id:
            return None
        return self._runs.get(self._selected_case_id)

    @staticmethod
    def _set_text(widget: scrolledtext.ScrolledText, content: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, content)
        widget.configure(state=tk.DISABLED)

    def on_close(self) -> None:
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
        self._stream.stop()
        self.destroy()


def main() -> None:
    app = ExtractionRunViewer()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
