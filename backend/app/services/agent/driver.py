"""
The Agent Driver.
Runs the agent loop: Snapshot -> Orchestrator -> Tool -> Ledger.
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

import yaml

from app.eventing import bind_event_case_id, get_event_producer, reset_event_case_id
from app.services.agent.state import AgentChecklistStore, Ledger
from app.services.agent.orchestrator import Orchestrator
from app.services.agent.snapshot import SnapshotBuilder
from app.services.agent.snapshot_formatter import SnapshotFormatter
from app.services.agent.tools import (
    ListDocumentsTool,
    ReadDocumentTool,
    SearchDocumentRegexTool,
    GetChecklistTool,
    UpdateChecklistTool,
    AppendChecklistTool,
)
from app.services.agent.tokenizer import TokenizerWrapper
from app.schemas.checklists import EvidenceCollection
from app.services.agent.schemas import OrchestratorAction

producer = get_event_producer(__name__)


class AgentDriver:
    def __init__(self, case_id: str, max_steps: int = 100, config_dir: Optional[Path] = None):
        self.case_id = case_id
        self.max_steps = max_steps
        self.config_dir = config_dir or (Path(__file__).parent / "config")

        self.checklist_config = {}
        self.user_instruction = ""
        self.task_constraints: List[str] = []
        self._load_config()

        # Initialize components
        self.store = AgentChecklistStore(checklist_config=self.checklist_config)
        self.ledger = Ledger()
        self.tokenizer = TokenizerWrapper()

        self.orchestrator = Orchestrator(config_dir=self.config_dir)
        self._register_tools()

        self.builder = SnapshotBuilder(
            case_id=case_id,
            store=self.store,
            ledger=self.ledger,
            tokenizer=self.tokenizer,
            checklist_config=self.checklist_config,
            user_instruction=self.user_instruction,
            task_constraints=self.task_constraints,
            recent_actions_detail=5,
        )

        # Run tracking
        self.action_history: List[Dict[str, Any]] = []
        self.last_tool_result: Optional[Dict[str, Any]] = None
        self.last_tool_name: Optional[str] = None
        self.stop_count = 0
        self.first_stop_step: Optional[int] = None

    def _load_config(self) -> None:
        checklist_file = self.config_dir / "checklist_configs" / "all" / "all_26_items.yaml"
        if not checklist_file.exists():
            checklist_file = self.config_dir / "checklist_config.yaml"

        if checklist_file.exists():
            with checklist_file.open("r", encoding="utf-8") as infile:
                checklist_data = yaml.safe_load(infile) or {}
            self.checklist_config = checklist_data.get("checklist_items", {})
            self.user_instruction = checklist_data.get("user_instruction", "")
            self.task_constraints = checklist_data.get("constraints", []) or []
        else:
            producer.warning("Checklist config not found", {"path": str(checklist_file)})
            self.checklist_config = {}
            self.user_instruction = ""
            self.task_constraints = []

    def _is_looping(self, action: OrchestratorAction, threshold: int = 3) -> bool:
        history = self.ledger.get_recent_history(n=threshold)
        if len(history) < threshold:
            return False

        for entry in history:
            if entry["tool"] != action.tool_name:
                return False
            if entry["args"] != action.tool_args:
                return False

        return True

    def _register_tools(self) -> None:
        tools = [
            ListDocumentsTool(),
            ReadDocumentTool(),
            SearchDocumentRegexTool(),
            GetChecklistTool(),
            UpdateChecklistTool(),
            AppendChecklistTool(),
        ]

        for tool in tools:
            tool.set_context(self.case_id, self.ledger, self.tokenizer, self.store)
            self.orchestrator.register_tool(tool)

    def _record_action(
        self,
        step: int,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Optional[Dict[str, Any]],
        auto_generated: bool = False,
    ) -> None:
        error = result.get("error") if isinstance(result, dict) else None
        validation_errors = result.get("validation_errors", []) if isinstance(result, dict) else []
        success = error is None and not validation_errors

        self.action_history.append(
            {
                "step": step,
                "action": {"tool": tool_name, "args": tool_args},
                "timestamp": datetime.now().isoformat(),
                "success": success,
                "error": error,
                "validation_errors": validation_errors,
                "tool_result": result,
                "auto_generated": auto_generated,
            }
        )

        self.ledger.record_action(
            step=step,
            tool_name=tool_name,
            args=tool_args,
            result=result,
        )

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "error":
            return tool_args

        tool = self.orchestrator._tools.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found"}

        try:
            if hasattr(tool, "safe_call"):
                return tool.safe_call(tool_args)
            return tool.call(tool_args)
        except Exception as exc:
            producer.error("Tool execution failed", {"error": str(exc)})
            return {"error": str(exc)}

    async def run(self) -> EvidenceCollection:
        token = bind_event_case_id(self.case_id)
        producer.info("Starting agent extraction", {"case_id": self.case_id})

        step = 1
        try:
            while step <= self.max_steps:
                producer.info("Agent step", {"step": step, "case_id": self.case_id})

                last_result = self.last_tool_result
                last_tool_name = self.last_tool_name
                self.last_tool_result = None
                self.last_tool_name = None

                try:
                    snapshot = self.builder.build(
                        step,
                        last_tool_result=last_result,
                        last_tool_name=last_tool_name,
                        action_history=self.action_history,
                        stop_count=self.stop_count,
                        first_stop_step=self.first_stop_step,
                    )
                except Exception:
                    producer.error(
                        "Failed to build snapshot",
                        {"step": step, "case_id": self.case_id},
                    )
                    break

                prompt = SnapshotFormatter.format_as_markdown(snapshot)
                action_plan = await self.orchestrator.decide_next_action(snapshot, prompt)

                if self._is_looping(action_plan):
                    producer.warning(
                        "Detected loop; stopping agent",
                        {"case_id": self.case_id, "tool": action_plan.tool_name},
                    )
                    self._record_action(
                        step=step,
                        tool_name="stop_loop",
                        tool_args={"reason": "Repetitive action detected"},
                        result={"status": "stopped_by_driver"},
                    )
                    break

                if action_plan.stop_decision:
                    self.stop_count += 1
                    stop_reason = action_plan.stop_reason or "No reason provided"
                    self._record_action(
                        step=step,
                        tool_name="stop",
                        tool_args={"reason": stop_reason},
                        result={"status": "stop_requested", "stop_count": self.stop_count},
                    )

                    if self.stop_count == 1:
                        self.first_stop_step = step
                        auto_step = step + 1
                        auto_result = self._execute_tool("get_checklist", {})
                        self._record_action(
                            step=auto_step,
                            tool_name="get_checklist",
                            tool_args={},
                            result=auto_result,
                            auto_generated=True,
                        )
                        self.last_tool_result = auto_result
                        self.last_tool_name = "get_checklist"
                        step = auto_step + 1
                        continue

                    if self.stop_count >= 3:
                        producer.warning(
                            "Forced stop after repeated attempts",
                            {"case_id": self.case_id, "stop_count": self.stop_count},
                        )

                    break

                tool_name = action_plan.tool_name
                tool_args = action_plan.tool_args or {}
                result = self._execute_tool(tool_name, tool_args)

                if tool_name == "list_documents" and isinstance(result, dict) and not result.get("error"):
                    self.builder.mark_documents_discovered()
                    self.ledger.mark_documents_discovered()

                self._record_action(step=step, tool_name=tool_name, tool_args=tool_args, result=result)

                self.last_tool_result = result
                self.last_tool_name = tool_name

                step += 1

            producer.info(
                "Agent run complete",
                {"case_id": self.case_id, "steps": step - 1},
            )
            return self.store.get_current_collection()
        finally:
            reset_event_case_id(token)


async def run_extraction_agent(case_id: str) -> EvidenceCollection:
    driver = AgentDriver(case_id)
    return await driver.run()
