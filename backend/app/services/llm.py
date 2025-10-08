from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from openai import AsyncOpenAI

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)
_file_logger = logging.getLogger("app.services.llm.file")
if not _file_logger.handlers:
    logs_root = Path(__file__).resolve().parents[2] / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(logs_root / "llm.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _file_logger.addHandler(handler)
    _file_logger.setLevel(logging.INFO)
    _file_logger.propagate = False


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMResult:
    text: str
    raw: Dict[str, Any] | None = None


def _strip_reasoning_tokens(text: str) -> str:
    return re.sub(r"<think>.*?</think>\n?", "", text, flags=re.DOTALL)


def _safe_json_dump(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(payload)


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
        schema_hint: str,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
    ) -> LLMResult:
        raise NotImplementedError

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
        schema_hint: str,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        json_prompt = (
            "Return only valid JSON conforming to this schema definition:\n"
            f"{schema_hint}\n\n"
            "Respond with JSON only, no natural language commentary.\n\n"
            f"{prompt}"
        )
        result = await self.generate_response(json_prompt, system=system)
        try:
            return json.loads(result.text)
        except json.JSONDecodeError as exc:
            logger.warning("Ollama JSON parsing failed: %s", exc)
            raise

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
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
        raw_response = await self._post("/api/chat", payload)
        message_block = raw_response.get("message") or {}
        content = message_block.get("content")
        if isinstance(content, list):
            text = "".join(part.get("text", "") for part in content)
        elif isinstance(content, str):
            text = content
        else:
            text = raw_response.get("response", "")
        cleaned = _strip_reasoning_tokens(text.strip())
        return LLMResult(text=cleaned, raw=raw_response)

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
        schema_hint: str,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        response = await self._client.responses.create(
            model=self._response_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Return a JSON object that satisfies this schema description. "
                        "Do not include any additional commentary.\n"
                        f"{schema_hint}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_output_tokens=self._defaults.max_output_tokens,
            reasoning={
                "effort": self._reasoning_effort,
            }
        )
        _file_logger.info(_safe_json_dump({
            "operation": "openai.generate_structured.response",
            "response": response.model_dump(),
        }))
        text = _strip_reasoning_tokens(_collect_openai_text(response)).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("OpenAI JSON parsing failed: %s", exc)
            raise

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
    ) -> LLMResult:
        input_messages: List[Dict[str, str]] = []
        if system:
            input_messages.append({"role": "system", "content": system})
        input_messages.extend({"role": message.role, "content": message.content} for message in messages)

        response = await self._client.responses.create(
            model=self._conversation_model,
            input=input_messages,
            max_output_tokens=self._defaults.max_output_tokens,
            reasoning={
                "effort": self._reasoning_effort,
            }
        )
        text = _strip_reasoning_tokens(_collect_openai_text(response)).strip()
        return LLMResult(text=text, raw=response.model_dump())

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
        schema_hint: str,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Return a deterministic placeholder suggestion list.
        return {
            "suggestions": [
                {
                    "id": "mock-1",
                    "type": "edit",
                    "comment": "Replace informal phrasing with formal legal language.",
                    "sourceDocument": "main-case",
                    "originalText": "stuff",
                    "text": "additional particulars",
                    "position": {"start": 0, "end": 5},
                }
            ]
        }

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

        if logger.isEnabledFor(logging.INFO):
            logger.info("Dispatching LLM request: %s", metadata)

        file_record = {
            "operation": operation,
            "system": system,
            "is_chat": is_chat,
            "model": metadata["model"],
            "request": request_payload if request_payload is not None else {"prompt": prompt_text},
        }
        _file_logger.info(_safe_json_dump(file_record))

    def _log_response(self, operation: str, raw: Any) -> None:
        if raw is None:
            return
        file_record = {
            "operation": operation,
            "response": raw,
        }
        _file_logger.info(_safe_json_dump(file_record))

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
        schema_hint: str,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._log_call(
            "generate_structured",
            system=system,
            prompt_text=prompt,
            request_payload={"prompt": prompt, "schema_hint": schema_hint, "system": system},
            is_chat=False,
        )
        result = await self._backend.generate_structured(prompt, schema_hint=schema_hint, system=system)
        self._log_response("generate_structured", result)
        return result

    async def chat(
        self,
        messages: List[LLMMessage],
        *,
        system: Optional[str] = None,
    ) -> str:
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
            },
            is_chat=True,
        )
        result = await self._backend.chat(messages, system=system)
        self._log_response("chat", getattr(result, "raw", None))
        return result.text

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
