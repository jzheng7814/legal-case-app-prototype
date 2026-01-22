"""
Orchestrator: The brain of the agent.
Decides the next action based on the Snapshot.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from app.services.llm import llm_service, LLMMessage
from app.services.agent.schemas import Snapshot, OrchestratorAction
from app.services.agent.tools import BaseTool

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self._tools: Dict[str, BaseTool] = {}
        # We might load prompts here, but simpler to embed or load from file if needed.
        # For now, we'll construct the system prompt dynamically or use the one from config.
    
    def register_tool(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def _build_system_prompt(self, snapshot: Snapshot) -> str:
        # Load prompt from file
        from pathlib import Path
        prompt_path = Path(__file__).parent / "prompts" / "default_system_prompt.md"
        try:
             base_prompt = prompt_path.read_text()
        except Exception:
             logger.warning("Could not load system prompt from file, using fallback.")
             base_prompt = "You are a document extraction agent. Extract the checklist items."

        tools_desc = []
        for name, tool in self._tools.items():
            desc = tool.describe()
            # simplified description
            tools_desc.append(f"- {name}: {desc['description']}")
            
        tool_list = "\n".join(tools_desc)
        
        return base_prompt.format(tool_list=tool_list)

    async def decide_next_action(self, snapshot: Snapshot, formatted_prompt: str) -> OrchestratorAction:
        """
        Ask the LLM for the next action.
        """
        system_prompt = self._build_system_prompt(snapshot)
        
        # The formatted_prompt comes from SnapshotFormatter (user message)
        
        try:
            # We use generate_text because we want flexible JSON, or structured?
            # The prompt says "Return specific JSON".
            # backend LLMService supports generate_structured if we have a pydantic model.
            # But the tool_args structure varies by tool.
            # So we define a generic "Decision" model or use raw JSON generation.
            
            # Let's try raw generation with JSON instruction to avoid strict schema validation issues on "tool_args" which is Any.
            response_text = await llm_service.generate_text(
                formatted_prompt,
                system=system_prompt
            )
            
            # Parse JSON
            # Ideally use a robust json parser
            cleaned = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            
            # Map to OrchestratorAction
            if data.get("decision") == "stop":
                return OrchestratorAction(
                    stop_decision=True,
                    stop_reason=data.get("reason"),
                    thought=data.get("thought")
                )
            
            return OrchestratorAction(
                tool_name=data.get("tool_name"),
                tool_args=data.get("tool_args"),
                thought=data.get("thought")
            )
            
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM response: %s", response_text)
            return OrchestratorAction(
                stop_decision=False,
                thought="Failed to parse JSON response",
                tool_name="parse_error", # Sentinel
                tool_args={"error": "Invalid JSON response from model", "raw": response_text}
            )
        except Exception as e:
            logger.exception("Orchestrator error")
            return OrchestratorAction(
                stop_decision=False,
                thought=f"Error: {str(e)}",
                tool_name="error",
                tool_args={"error": str(e)}
            )
