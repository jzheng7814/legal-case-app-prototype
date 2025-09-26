from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "legal-case-backend"
    environment: str = "development"
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: float = 30.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    use_mock_llm: bool = False
    document_root: str = "data/documents"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="LEGAL_CASE_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
