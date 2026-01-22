"""
The Agent Driver.
Runs the agent loop: Snapshot -> Orchestrator -> Tool -> Ledger.
"""

import logging
import asyncio
from typing import Optional, Dict, Any

from app.services.agent.state import AgentChecklistStore, Ledger
from app.services.agent.orchestrator import Orchestrator
from app.services.agent.snapshot import SnapshotBuilder
from app.services.agent.snapshot_formatter import SnapshotFormatter
from app.services.agent.tools import (
    ListDocumentsTool, ReadDocumentTool, SearchDocumentRegexTool,
    GetChecklistTool, UpdateChecklistTool, AppendChecklistTool
)
from app.services.agent.tokenizer import TokenizerWrapper
from app.schemas.checklists import EvidenceCollection

logger = logging.getLogger(__name__)

class AgentDriver:
    def __init__(self, case_id: str, max_steps: int = 50):
        self.case_id = case_id
        self.max_steps = max_steps
        
        # Initialize components
        self.store = AgentChecklistStore()
        self.ledger = Ledger()
        self.tokenizer = TokenizerWrapper()
        
        self.orchestrator = Orchestrator()
        self._register_tools()
        
        self.builder = SnapshotBuilder(
            case_id=case_id,
            store=self.store,
            ledger=self.ledger,
            tokenizer=self.tokenizer
        )

    def _register_tools(self):
        # Instantiate tools
        tools = [
            ListDocumentsTool(),
            ReadDocumentTool(),
            SearchDocumentRegexTool(),
            GetChecklistTool(),
            UpdateChecklistTool(),
            AppendChecklistTool()
        ]
        
        # Inject context and register
        for tool in tools:
            tool.set_context(self.case_id, self.ledger, self.tokenizer, self.store)
            self.orchestrator.register_tool(tool)

    async def run(self) -> EvidenceCollection:
        """
        Execute the agent loop.
        """
        logger.info("Starting agent extraction for case %s", self.case_id)
        
        step = 1
        while step <= self.max_steps:
            logger.info("Agent Step %d", step)
            
            # 1. Build Snapshot
            try:
                snapshot = self.builder.build(step)
            except Exception as e:
                logger.exception("Failed to build snapshot at step %d", step)
                break

            # 2. Format Prompt
            prompt = SnapshotFormatter.format_as_markdown(snapshot)
            
            # 3. Decide Action
            action_plan = await self.orchestrator.decide_next_action(snapshot, prompt)
            
            # Check for stop
            if action_plan.stop_decision:
                logger.info("Agent decided to stop: %s", action_plan.stop_reason)
                self.ledger.record_action(
                    step=step,
                    tool_name="stop",
                    args={"reason": action_plan.stop_reason},
                    result={"status": "stopped"}
                )
                break
            
            # 4. Execute Tool
            tool_name = action_plan.tool_name
            tool_args = action_plan.tool_args or {}
            
            tool = self.orchestrator._tools.get(tool_name)
            result = None
            if tool:
                try:
                    logger.info("Executing tool %s with args %s", tool_name, tool_args)
                    # Validate input?
                    result = tool.call(tool_args)
                except Exception as e:
                    logger.error("Tool execution failed: %s", e)
                    result = {"error": str(e)}
            else:
                logger.warning("Tool not found: %s", tool_name)
                result = {"error": f"Tool '{tool_name}' not found"}

            # 5. Update Ledger
            self.ledger.record_action(
                step=step,
                tool_name=tool_name,
                args=tool_args,
                result=result
            )
            
            step += 1
            
        logger.info("Agent run complete after %d steps", step - 1)
        return self.store.get_current_collection()

# Convenience entry point
async def run_extraction_agent(case_id: str) -> EvidenceCollection:
    driver = AgentDriver(case_id)
    return await driver.run()
