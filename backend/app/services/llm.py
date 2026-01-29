from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.eventing import EventVisibility, get_event_producer

producer = get_event_producer(__name__)


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMResult:
    text: str
    raw: Dict[str, Any] | None = None
    tool_outputs: List["LLMToolHandlerResult"] = field(default_factory=list)
    tool_calls: List["LLMToolCall"] = field(default_factory=list)


@dataclass
class LLMToolCall:
    name: str
    arguments: str
    call_id: str


@dataclass
class LLMToolHandlerResult:
    call: LLMToolCall
    output: str
    metadata: Dict[str, Any] | None = None


def _strip_reasoning_tokens(text: str) -> str:
    return re.sub(r"<think>.*?</think>\n?", "", text, flags=re.DOTALL)


def _schema_from_model(model: type[BaseModel]) -> str:
    schema = model.model_json_schema(by_alias=True)
    return json.dumps(schema, indent=2, sort_keys=True)


class LLMBackend:
    async def generate_response(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> LLMResult:
        raise NotImplementedError

    async def generate_structured(
        self,
        prompt: str,
        *,
        response_model: type[BaseModel],
        schema: str,
        system: Optional[str] = None,
    ) -> BaseModel:
        raise NotImplementedError

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResult:
        raise NotImplementedError

    async def chat_with_tools(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_handler: Optional[Callable[[LLMToolCall], Awaitable[LLMToolHandlerResult]]] = None,
    ) -> LLMResult:
        return await self.chat(messages, system=system)

    async def aclose(self) -> None:
        return None


class OllamaBackend(LLMBackend):
    def __init__(self, settings: Settings):
        config = settings.model.ollama
        if not config:
            raise RuntimeError("Ollama configuration is missing")
        self._defaults = settings.model.defaults
        timeout = httpx.Timeout(config.timeout_seconds)
        self._client = httpx.AsyncClient(base_url=config.base_url, timeout=timeout)
        self._lock = asyncio.Lock()
        self._response_model = config.response_model
        self._conversation_model = config.conversation_model_name()

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
        return response.json()

    def _build_options(self) -> Dict[str, Any]:
        return {
            "temperature": self._defaults.temperature,
            "num_predict": self._defaults.max_output_tokens,
            "num_ctx": 32768,
        }

    async def generate_response(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> LLMResult:
        payload: Dict[str, Any] = {
            "model": self._response_model,
            "prompt": prompt,
            "stream": False,
            "options": self._build_options(),
        }
        if system:
            payload["system"] = system
        raw_response = await self._post("/api/generate", payload)
        text = _strip_reasoning_tokens(raw_response.get("response", "").strip())
        return LLMResult(text=text, raw=raw_response)

    async def generate_structured(
        self,
        prompt: str,
        *,
        response_model: type[BaseModel],
        schema: str,
        system: Optional[str] = None,
    ) -> BaseModel:
        json_prompt = (
            "Return only valid JSON conforming to this schema definition:\n"
            f"{schema}\n\n"
            "Respond with JSON only, no natural language commentary.\n\n"
            f"{prompt}"
        )
        payload: Dict[str, Any] = {
            "model": self._response_model,
            "prompt": json_prompt,
            "stream": False,
            "format": "json",
            "options": self._build_options(),
        }
        if system:
            payload["system"] = system

        raw_response = await self._post("/api/generate", payload)
        text = _strip_reasoning_tokens(raw_response.get("response", "").strip())
        result = LLMResult(text=text, raw=raw_response)
        try:
            return response_model.model_validate_json(result.text)
        except (ValidationError, ValueError) as exc:
            producer.warning("Ollama structured parsing failed", {"error": str(exc)})
            raise

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResult:
        payload_messages: List[Dict[str, str]] = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend({"role": message.role, "content": message.content} for message in messages)

        payload: Dict[str, Any] = {
            "model": self._conversation_model,
            "messages": payload_messages,
            "stream": False,
            "options": self._build_options(),
        }

        if tools:
            payload["tools"] = tools

        raw_response = await self._post("/api/chat", payload)
        message_block = raw_response.get("message") or {}
        
        tool_calls = message_block.get("tool_calls")
        llm_tool_calls = []
        
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                llm_tool_calls.append(
                    LLMToolCall(
                        name=func.get("name", ""),
                        arguments=json.dumps(func.get("arguments", {})),
                        call_id="" # Ollama might not return call_id
                    )
                )

        content = message_block.get("content")
        if isinstance(content, list):
            text = "".join(part.get("text", "") for part in content)
        elif isinstance(content, str):
            text = content
        else:
            text = raw_response.get("response", "")
        
        cleaned = _strip_reasoning_tokens(text.strip()) if text else ""
        
        return LLMResult(
            text=cleaned, 
            raw=raw_response,
            tool_outputs=[],
            tool_calls=llm_tool_calls
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class OpenAIBackend(LLMBackend):
    def __init__(self, settings: Settings):
        config = settings.model.openai
        if not config:
            raise RuntimeError("OpenAI configuration is missing")
        api_key = settings.resolve_openai_api_key()
        if not api_key:
            raise RuntimeError("OpenAI API key is not configured")
        self._defaults = settings.model.defaults
        self._client = AsyncOpenAI(api_key=api_key)
        self._response_model = config.response_model
        self._conversation_model = config.conversation_model_name()
        self._reasoning_effort = config.reasoning_effort

    def _normalize_openai_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for tool in tools:
            if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
                func = tool["function"]
                entry = {
                    "type": "function",
                    "name": func.get("name"),
                    "description": func.get("description"),
                    "parameters": func.get("parameters"),
                }
                if func.get("strict") is True:
                    entry["strict"] = True
                normalized.append(entry)
            else:
                normalized.append(tool)
        return normalized

    def _build_input(self, prompt: str, *, system: Optional[str] = None) -> List[Dict[str, str]]:
        inputs: List[Dict[str, str]] = []
        if system:
            inputs.append({"role": "system", "content": system})
        inputs.append({"role": "user", "content": prompt})
        return inputs

    async def generate_response(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> LLMResult:
        response = await self._client.responses.create(
            model=self._response_model,
            input=self._build_input(prompt, system=system),
            max_output_tokens=self._defaults.max_output_tokens,
            reasoning={
                "effort": self._reasoning_effort,
            }
        )
        text = _strip_reasoning_tokens(_collect_openai_text(response))
        return LLMResult(text=text.strip(), raw=response.model_dump())

    async def generate_structured(
        self,
        prompt: str,
        *,
        response_model: type[BaseModel],
        schema: str,
        system: Optional[str] = None,
    ) -> BaseModel:
        structured_instructions = (
            "Return a JSON object that satisfies this schema description. "
            "Do not include any additional commentary.\n"
            f"{schema}"
        )
        combined_system = structured_instructions if system is None else f"{structured_instructions}\n\n{system}"
        response = await self._client.responses.parse(
            model=self._response_model,
            input=[
                {
                    "role": "system",
                    "content": combined_system,
                },
                {"role": "user", "content": prompt},
            ],
            max_output_tokens=self._defaults.max_output_tokens,
            reasoning={
                "effort": self._reasoning_effort,
            },
            text_format=response_model,
        )
        producer.debug(
            "OpenAI structured response",
            {
                "operation": "openai.generate_structured.response",
                "response": response.model_dump(),
            },
        )
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            producer.warning("OpenAI structured output missing parsed payload")
            raise ValueError("Structured output did not produce parsed content")
        if not isinstance(parsed, response_model):
            try:
                return response_model.model_validate(parsed)
            except ValidationError as exc:
                producer.warning("OpenAI structured output validation failed", {"error": str(exc)})
                raise
        return parsed

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResult:
        input_messages: List[Dict[str, str]] = []
        if system:
            input_messages.append({"role": "system", "content": system})
        input_messages.extend({"role": message.role, "content": message.content} for message in messages)

        kwargs = {
            "model": self._conversation_model,
            "input": input_messages,
            "max_output_tokens": self._defaults.max_output_tokens,
            "reasoning": {
                "effort": self._reasoning_effort,
            }
        }

        if tools:
            kwargs["tools"] = self._normalize_openai_tools(tools)
            kwargs["tool_choice"] = "required"
            kwargs["parallel_tool_calls"] = False

        response = await self._client.responses.create(**kwargs)
        
        text = _strip_reasoning_tokens(_collect_openai_text(response)).strip()
        
        llm_tool_calls = []
        output = getattr(response, "output", None) or []
        for item in output:
             if getattr(item, "type", None) == "function_call":
                 llm_tool_calls.append(
                     LLMToolCall(
                         name=item.name,
                         arguments=item.arguments,
                         call_id=item.call_id
                     )
                 )
        
        return LLMResult(text=text, raw=response.model_dump(), tool_calls=llm_tool_calls)

    async def chat_with_tools(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_handler: Optional[Callable[[LLMToolCall], Awaitable[LLMToolHandlerResult]]] = None,
    ) -> LLMResult:
        if not tools or tool_handler is None:
            return await self.chat(messages, system=system)

        conversation: List[Any] = []
        if system:
            conversation.append({"role": "system", "content": system})
        conversation.extend({"role": message.role, "content": message.content} for message in messages)

        handler_results: List[LLMToolHandlerResult] = []

        response = await self._client.responses.create(
            model=self._conversation_model,
            input=conversation,
            tools=self._normalize_openai_tools(tools),
            max_output_tokens=self._defaults.max_output_tokens,
            reasoning={
                "effort": self._reasoning_effort,
            },
            tool_choice="required",
            parallel_tool_calls=False,
        )
        conversation.extend(response.output or [])

        while True:
            tool_calls = [
                item
                for item in (response.output or [])
                if getattr(item, "type", None) == "function_call"
            ]
            if not tool_calls:
                text = _strip_reasoning_tokens(_collect_openai_text(response)).strip()
                return LLMResult(text=text, raw=response.model_dump(), tool_outputs=handler_results)

            for call in tool_calls:
                llm_call = LLMToolCall(name=call.name, arguments=call.arguments, call_id=call.call_id)
                handler_result = await tool_handler(llm_call)
                output_payload = handler_result.output or "{}"
                handler_result.output = output_payload
                handler_results.append(handler_result)
                conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output_payload,
                    }
                )

            response = await self._client.responses.create(
                model=self._conversation_model,
                input=conversation,
                tools=self._normalize_openai_tools(tools),
                max_output_tokens=self._defaults.max_output_tokens,
                reasoning={
                    "effort": self._reasoning_effort,
                },
                tool_choice="required",
                parallel_tool_calls=False,
            )
            conversation.extend(response.output or [])

    async def aclose(self) -> None:
        await self._client.close()


class MockBackend(LLMBackend):
    async def generate_response(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> LLMResult:
        snippet = prompt.splitlines()
        faux_summary = " ".join(line.strip() for line in snippet if line.strip())
        text = (
            "MOCK RESPONSE:\n"
            f"System: {system}\n" if system else ""
        ) + faux_summary
        return LLMResult(text=text)

    async def generate_structured(
        self,
        prompt: str,
        *,
        response_model: type[BaseModel],
        schema: str,
        system: Optional[str] = None,
    ) -> BaseModel:
        if response_model.__name__ == "ChecklistExtractionPayload":
            payload = {"reasoning": "Mock reasoning", "extracted": []}
            return response_model.model_validate(payload)
        if response_model.__name__ == "SummaryChecklistExtractionPayload":
            return response_model.model_validate({"items": []})
        try:
            return response_model.model_validate({})
        except ValidationError as exc:
            raise RuntimeError(f"Mock backend cannot satisfy response model {response_model.__name__}") from exc

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
    ) -> LLMResult:
        last_user = next((message for message in reversed(messages) if message.role == "user"), None)
        text = "MOCK CHAT RESPONSE"
        if last_user:
            text += f": {last_user.content[:80]}"
        if system:
            text += f" (system: {system[:40]})"
        return LLMResult(text=text)


class LLMService:
    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        if self._settings.use_mock_llm or self._settings.model.provider == "mock":
            self._backend: LLMBackend = MockBackend()
        else:
            provider = self._settings.model.provider
            if provider == "openai":
                self._backend = OpenAIBackend(self._settings)
            elif provider == "ollama":
                self._backend = OllamaBackend(self._settings)
            else:
                raise ValueError(f"Unsupported LLM provider: {provider}")

    def _resolve_model_name(self, *, is_chat: bool = False) -> str:
        config = self._settings.model
        if config.provider == "openai" and config.openai:
            return (
                config.openai.conversation_model_name()
                if is_chat
                else config.openai.response_model
            )
        if config.provider == "ollama" and config.ollama:
            return (
                config.ollama.conversation_model_name()
                if is_chat
                else config.ollama.response_model
            )
        return "unknown"

    def _log_call(
        self,
        operation: str,
        *,
        system: Optional[str],
        prompt_text: Optional[str] = None,
        request_payload: Optional[Dict[str, Any]] = None,
        is_chat: bool = False,
    ) -> None:
        preview = (prompt_text[:160] + "...") if prompt_text and len(prompt_text) > 160 else prompt_text
        metadata: Dict[str, Any] = {
            "operation": operation,
            "provider": self._settings.model.provider,
            "model": self._resolve_model_name(is_chat=is_chat),
            "has_system_prompt": bool(system),
        }
        if prompt_text is not None:
            metadata["prompt_length"] = len(prompt_text)
        if preview:
            metadata["prompt_preview"] = preview

        if producer.is_enabled(EventVisibility.INFO):
            producer.info("Dispatching LLM request", metadata)

        file_record = {
            "operation": operation,
            "system": system,
            "is_chat": is_chat,
            "model": metadata["model"],
            "request": request_payload if request_payload is not None else {"prompt": prompt_text},
        }
        producer.debug("LLM request record", file_record)

    def _log_response(self, operation: str, raw: Any) -> None:
        if raw is None:
            return
        file_record = {
            "operation": operation,
            "response": raw,
        }
        producer.debug("LLM response record", file_record)

    async def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> str:
        self._log_call(
            "generate_text",
            system=system,
            prompt_text=prompt,
            request_payload={"prompt": prompt, "system": system},
            is_chat=False,
        )
        result = await self._backend.generate_response(prompt, system=system)
        self._log_response("generate_text", getattr(result, "raw", None))
        return result.text

    async def generate_structured(
        self,
        prompt: str,
        *,
        response_model: type[BaseModel],
        system: Optional[str] = None,
    ) -> BaseModel:
        schema_hint = _schema_from_model(response_model)
        self._log_call(
            "generate_structured",
            system=system,
            prompt_text=prompt,
            request_payload={
                "prompt": prompt,
                "response_model": response_model.__name__,
                "schema_hint": schema_hint,
                "system": system,
            },
            is_chat=False,
        )
        result = await self._backend.generate_structured(
            prompt,
            response_model=response_model,
            schema=schema_hint,
            system=system,
        )
        if isinstance(result, BaseModel):
            serialized = result.model_dump(by_alias=True)
        else:
            serialized = result
        self._log_response("generate_structured", serialized)
        return result

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResult:
        preview = ""
        if messages:
            last = messages[-1]
            preview = f"{last.role}: {last.content}"
        self._log_call(
            "chat",
            system=system,
            prompt_text=preview,
            request_payload={
                "messages": [message.__dict__ for message in messages],
                "system": system,
                "tools": tools,
            },
            is_chat=True,
        )
        result = await self._backend.chat(messages, system=system, tools=tools)
        self._log_response("chat", getattr(result, "raw", None))

        return result



    async def chat_with_tools(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_handler: Optional[Callable[[LLMToolCall], Awaitable[LLMToolHandlerResult]]] = None,
    ) -> LLMResult:
        preview = ""
        if messages:
            last = messages[-1]
            preview = f"{last.role}: {last.content}"
        self._log_call(
            "chat_with_tools",
            system=system,
            prompt_text=preview,
            request_payload={
                "messages": [message.__dict__ for message in messages],
                "system": system,
                "tools": tools,
            },
            is_chat=True,
        )
        result = await self._backend.chat_with_tools(
            messages,
            system=system,
            tools=tools,
            tool_handler=tool_handler,
        )
        self._log_response("chat_with_tools", getattr(result, "raw", None))
        return result

    async def shutdown(self) -> None:
        await self._backend.aclose()


def _collect_openai_text(response: Any) -> str:
    chunks: List[str] = []
    output = getattr(response, "output", None) or []
    for item in output:
        content_items = getattr(item, "content", None) or []
        for content in content_items:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    out = "".join(chunks)
    if out:
        return out
    fallback = getattr(response, "output_text", None)
    if fallback:
        return fallback
    return ""

llm_service = LLMService()
