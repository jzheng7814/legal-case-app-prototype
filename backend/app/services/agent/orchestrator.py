"""
Orchestrator: The brain of the agent.
Decides the next action based on the Snapshot using Native Tool Calling.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from app.services.llm import llm_service, LLMMessage, LLMResult
from app.services.agent.schemas import Snapshot, OrchestratorAction
from app.services.agent.tools import BaseTool, StopTool

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self._tools: Dict[str, BaseTool] = {}
        
        # Always register the StopTool implicitly or explicitly
        self._stop_tool = StopTool()
    
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
             base_prompt = "You are a document extraction agent. Extract the checklist items. Use the provided tools."

        # The prompt template no longer needs {tool_list}
        # If there are any residual formatting keys, handle gracefully
        try:
            return base_prompt.format(tool_list="")
        except Exception:
            return base_prompt

    def _convert_to_tool_schema(self, tool: BaseTool) -> Dict[str, Any]:
        """
        Convert internal Tool representation to OpenAI/Ollama-compatible tool schema.
        """
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.get_input_schema()
            }
        }

    async def decide_next_action(self, snapshot: Snapshot, formatted_prompt: str) -> OrchestratorAction:
        """
        Ask the LLM for the next action using native tool calling.
        """
        system_prompt = self._build_system_prompt(snapshot)
        
        # Prepare tools
        # Include all registered tools + StopTool
        all_tools = list(self._tools.values())
        # Ensure StopTool is present if not already (though usually handled distinct)
        if "stop_task" not in self._tools:
            all_tools.append(self._stop_tool)
            
        tool_schemas = [self._convert_to_tool_schema(t) for t in all_tools]
        
        # User message is the formatted snapshot
        messages = [LLMMessage(role="user", content=formatted_prompt)]
        
        try:
            # Native Tool Call via LLM Service
            result: LLMResult = await llm_service.chat(
                messages,
                system=system_prompt,
                tools=tool_schemas
            )
            
            # Parse result for tool calls
            if result.tool_calls:
                # Agent generally takes one action per turn, so look at the first one
                # Logic could be extended to support parallel tool calls later
                call = result.tool_calls[0]
                
                tool_name = call.name
                try:
                    tool_args = json.loads(call.arguments)
                except json.JSONDecodeError:
                    return OrchestratorAction(
                        thought=result.text,
                        stop_decision=False,
                        tool_name="error",
                        tool_args={"error": f"Failed to parse arguments for tool {tool_name}"}
                    )
                
                # Handle Stop Tool specially
                if tool_name == "stop_task":
                    return OrchestratorAction(
                        thought=result.text or f"Decided to stop: {tool_args.get('reason')}",
                        stop_decision=True,
                        stop_reason=tool_args.get("reason", "No reason provided"),
                        tool_name=tool_name,
                        tool_args=tool_args
                    )
                
                return OrchestratorAction(
                    thought=result.text or f"Calling tool {tool_name}",
                    stop_decision=False,
                    tool_name=tool_name,
                    tool_args=tool_args
                )
            
            # Fallback: No tool call found
            # The model might have just outputted text thinking.
            # We can treat this as a "thought" step or a failures depending on strictness.
            # For now, let's return an error action prompting retry, or just the thought.
            return OrchestratorAction(
                thought=result.text,
                stop_decision=False,
                tool_name="error",
                tool_args={"error": "Model did not call any tool. Please use one of the provided tools."}
            )
            
        except Exception as e:
            logger.exception("Orchestrator error")
            return OrchestratorAction(
                thought=f"Error during decision making: {str(e)}",
                stop_decision=False,
                tool_name="error",
                tool_args={"error": str(e)}
            )
