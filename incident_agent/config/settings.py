"""Typed, environment-driven application configuration.

Design rationale
-----------------
We use `pydantic-settings` with `env_nested_delimiter="__"` so a single
`.env` file (or process environment) can populate a *tree* of settings
objects, e.g. `ANTHROPIC__API_KEY`, `LLM__PRIMARY_PROVIDER`. This gives us:

1. One source of truth for configuration, validated at process start
   (fail fast on missing/invalid config instead of failing deep inside a
   graph run).
2. Provider switching (Anthropic -> OpenAI -> Azure OpenAI) as a pure
   config change (`LLM__PRIMARY_PROVIDER=openai`), which is exactly what
   the Strategy pattern in `services/llm_factory.py` (Phase 3+) needs.
3. Testability: every settings group can be constructed directly in unit
   tests without touching environment variables at all.

`get_settings()` is process-cached with `lru_cache` so the (relatively
expensive) validation and `.env` file read happens once per process,
mirroring FastAPI's recommended settings pattern.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

LLMProvider = Literal["anthropic", "openai", "azure_openai"]
Environment = Literal["local", "development", "staging", "production", "test"]


class AnthropicSettings(BaseModel):
    """Credentials/model selection for the primary LLM provider."""

    api_key: SecretStr | None = None
    model: str = "claude-sonnet-5"
    fallback_model: str = "claude-haiku-4-5-20251001"


class OpenAISettings(BaseModel):
    """Credentials/model selection for the first fallback provider."""

    api_key: SecretStr | None = None
    model: str = "gpt-4.1"


class AzureOpenAISettings(BaseModel):
    """Credentials/model selection for the second fallback provider.

    Azure OpenAI addresses a deployment (not a raw model name), so it
    needs an endpoint + deployment + API version in addition to a key.
    """

    api_key: SecretStr | None = None
    endpoint: str | None = None
    deployment: str | None = None
    api_version: str = "2024-10-21"


class LLMSettings(BaseModel):
    """Provider-agnostic generation parameters plus failover policy.

    `primary_provider`/`fallback_providers` are consumed by the
    `LLMClientFactory` (Strategy pattern) to build a chain of chat models
    that are tried in order -- see `services/llm_factory.py`.
    """

    primary_provider: LLMProvider = "anthropic"
    fallback_providers: list[LLMProvider] = Field(default_factory=lambda: ["openai", "azure_openai"])
    temperature: float = 0.1
    max_tokens: int = 4096
    request_timeout_seconds: float = 60.0
    max_retries: int = 2

    @model_validator(mode="after")
    def _fallbacks_exclude_primary(self) -> "LLMSettings":
        self.fallback_providers = [p for p in self.fallback_providers if p != self.primary_provider]
        return self


class ChromaSettings(BaseModel):
    """Vector store location and collection naming for the RAG pipeline."""

    persist_directory: str = str(PROJECT_ROOT / "data" / "chroma")
    collection_name: str = "incident_knowledge_base"
    embedding_model: str = "all-MiniLM-L6-v2"


class CheckpointSettings(BaseModel):
    """SQLite-backed LangGraph checkpointer configuration."""

    database_path: str = str(PROJECT_ROOT / "data" / "checkpoints" / "checkpoints.sqlite")


class MemorySettings(BaseModel):
    """SQLite-backed long-term/episodic memory store (separate DB from checkpoints)."""

    database_path: str = str(PROJECT_ROOT / "data" / "sqlite" / "memory.sqlite")


class LangSmithSettings(BaseModel):
    """Observability configuration -- toggled independently of tracing libs
    being installed, so local dev without a LangSmith account still runs.
    """

    tracing_enabled: bool = False
    api_key: SecretStr | None = None
    project: str = "enterprise-incident-resolution-agent"
    endpoint: str = "https://api.smith.langchain.com"


class APISettings(BaseModel):
    """FastAPI/uvicorn transport configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    api_key: SecretStr | None = None
    """Optional shared-secret for inbound request auth (X-API-Key header)."""


class Settings(BaseSettings):
    """Root settings object -- import `get_settings()`, never this class directly."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Enterprise Incident Resolution Agent"
    environment: Environment = "local"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False
    """JSON logs in production/staging; human-readable console logs locally."""

    confidence_threshold: float = 0.75
    """Below this, the graph routes back through Replan/Retry instead of Human Approval."""
    max_replan_attempts: int = 3

    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    azure_openai: AzureOpenAISettings = Field(default_factory=AzureOpenAISettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    chroma: ChromaSettings = Field(default_factory=ChromaSettings)
    checkpoint: CheckpointSettings = Field(default_factory=CheckpointSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)
    api: APISettings = Field(default_factory=APISettings)

    def ensure_data_directories(self) -> None:
        """Create local data directories used by SQLite/Chroma if absent.

        Called once at application startup rather than at import time, so
        importing this module never has filesystem side effects (keeps
        unit tests hermetic).
        """
        for path_str in (
            self.chroma.persist_directory,
            str(Path(self.checkpoint.database_path).parent),
            str(Path(self.memory.database_path).parent),
        ):
            Path(path_str).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide `Settings` singleton (cached after first call)."""
    return Settings()
