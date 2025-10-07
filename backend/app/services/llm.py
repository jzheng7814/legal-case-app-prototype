from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
import re

import httpx

from app.core.config import get_settings, Settings

logger = logging.getLogger(__name__)

@dataclass
class LLMResult:
    text: str
    raw: Dict[str, Any] | None = None


class LLMBackend:
    async def generate(self, prompt: str, *, system: Optional[str] = None, **kwargs: Any) -> LLMResult:
        raise NotImplementedError

    async def generate_json(self, prompt: str, *, schema_hint: str, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError


class OllamaBackend(LLMBackend):
    def __init__(self, settings: Settings):
        self._settings = settings
        timeout = httpx.Timeout(settings.ollama_timeout_seconds)
        self._client = httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=timeout)
        self._lock = asyncio.Lock()

    async def _post_generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            response = await self._client.post("/api/generate", json=payload)
            response.raise_for_status()
        return response.json()

    async def generate(self, prompt: str, *, system: Optional[str] = None, **kwargs: Any) -> LLMResult:
        options = {
            "temperature": kwargs.get("temperature", self._settings.llm_temperature),
            "num_predict": kwargs.get("max_tokens", self._settings.llm_max_tokens),
        }
        payload: Dict[str, Any] = {
            "model": self._settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        if system:
            payload["system"] = system
        raw_response = await self._post_generate(payload)
        text = raw_response.get("response", "").strip()
        text = re.sub(r"<think>.*?</think>\n?", "", text, flags=re.DOTALL)
        return LLMResult(text=text, raw=raw_response)

    async def generate_json(self, prompt: str, *, schema_hint: str, **kwargs: Any) -> Dict[str, Any]:
        # Ask Ollama to emit JSON and attempt to parse the final response.
        json_prompt = (
            f"You must return JSON that matches this schema: {schema_hint}.\n"
            "Return only valid JSON without commentary.\n\n"
            f"{prompt}"
        )
        result = await self.generate(json_prompt, **kwargs)
        try:
            text = re.sub(r"<think>.*?</think>\n?", "", result.text, flags=re.DOTALL)
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to decode JSON response: %s", exc)
            raise

    async def aclose(self) -> None:
        await self._client.aclose()


class MockBackend(LLMBackend):
    async def generate(self, prompt: str, *, system: Optional[str] = None, **kwargs: Any) -> LLMResult:
        snippet = prompt.splitlines()[:3]
        faux_summary = " ".join(line.strip() for line in snippet if line.strip())
        text = (
            "MOCK RESPONSE:\n"
            f"System: {system}\n" if system else ""
        ) + faux_summary
        return LLMResult(text=text)

    async def generate_json(self, prompt: str, *, schema_hint: str, **kwargs: Any) -> Dict[str, Any]:
        # Return a deterministic placeholder suggestion list.
        return {
            "suggestions": [
                {
                    "id": "mock-1",
                    "type": "edit",
                    "comment": "Replace informal phrasing with formal legal language.",
                    "sourceDocument": "main-case",
                    "originalText": "stuff",
                    "suggestedText": "additional particulars",
                    "position": {"start": 0, "end": 5},
                }
            ]
        }


class LLMService:
    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        if self._settings.use_mock_llm:
            self._backend: LLMBackend = MockBackend()
        else:
            self._backend = OllamaBackend(self._settings)

    async def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        result = await self._backend.generate(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return result.text

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema_hint: str,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        return await self._backend.generate_json(prompt, schema_hint=schema_hint, temperature=temperature)

    async def shutdown(self) -> None:
        if isinstance(self._backend, OllamaBackend):
            await self._backend.aclose()


llm_service = LLMService()
