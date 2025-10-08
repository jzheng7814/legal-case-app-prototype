from __future__ import annotations

import json
import os
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelDefaults(BaseModel):
    temperature: float = 0.3
    max_output_tokens: int = 4096


class OpenAIModelConfig(BaseModel):
    response_model: str
    conversation_model: Optional[str] = None
    api_key: Optional[str] = None

    def conversation_model_name(self) -> str:
        return self.conversation_model or self.response_model


class OllamaModelConfig(BaseModel):
    base_url: str
    timeout_seconds: float = 60.0
    response_model: str
    conversation_model: Optional[str] = None

    def conversation_model_name(self) -> str:
        return self.conversation_model or self.response_model


class ModelConfig(BaseModel):
    provider: Literal["openai", "ollama", "mock"] = "openai"
    defaults: ModelDefaults = Field(default_factory=ModelDefaults)
    openai: Optional[OpenAIModelConfig] = None
    ollama: Optional[OllamaModelConfig] = None


class AppConfig(BaseModel):
    model: ModelConfig


class Settings(BaseSettings):
    app_name: str = "legal-case-backend"
    environment: str = "development"
    use_mock_llm: bool = False
    document_root: str = "data/documents"
    config_path: str = "config/app.config.json"
    openai_api_key: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="LEGAL_CASE_")

    @cached_property
    def app_config(self) -> AppConfig:
        config_path = Path(self.config_path)
        if not config_path.is_absolute():
            backend_root = Path(__file__).resolve().parents[2]
            config_path = backend_root / config_path
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            return AppConfig.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(f"Failed to load configuration from {config_path}: {exc}") from exc

    @property
    def model(self) -> ModelConfig:
        return self.app_config.model

    def resolve_openai_api_key(self) -> Optional[str]:
        configured = self.openai_api_key or (self.model.openai.api_key if self.model.openai else None)
        return configured or os.getenv("OPENAI_API_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
