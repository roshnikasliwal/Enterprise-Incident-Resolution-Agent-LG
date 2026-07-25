"""Phase 1 smoke tests.

These exist to prove the project *scaffolding* itself is sound before any
domain logic is layered on top: settings validate, env-var overrides and
nested-delimiter parsing work, directories are created on demand (not at
import time), and logging configures exactly once per process.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from incident_agent.config.logging_config import configure_logging, get_logger
from incident_agent.config.settings import Settings, get_settings


@pytest.mark.unit
class TestSettings:
    def test_defaults_construct_without_env_file(self) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.app_name == "Enterprise Incident Resolution Agent"
        assert settings.llm.primary_provider == "anthropic"
        assert settings.confidence_threshold == pytest.approx(0.75)

    def test_get_settings_is_cached_singleton(self) -> None:
        assert get_settings() is get_settings()

    def test_nested_env_delimiter_overrides_llm_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM__PRIMARY_PROVIDER", "openai")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.llm.primary_provider == "openai"

    def test_fallback_providers_never_include_primary(self) -> None:
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            llm={"primary_provider": "openai", "fallback_providers": ["anthropic", "openai", "azure_openai"]},
        )
        assert "openai" not in settings.llm.fallback_providers
        assert settings.llm.fallback_providers == ["anthropic", "azure_openai"]

    def test_secrets_are_not_rendered_in_repr(self) -> None:
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            anthropic={"api_key": "sk-ant-super-secret"},
        )
        assert "sk-ant-super-secret" not in repr(settings.anthropic)

    def test_ensure_data_directories_creates_expected_paths(self, tmp_path: Path) -> None:
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            chroma={"persist_directory": str(tmp_path / "chroma")},
            checkpoint={"database_path": str(tmp_path / "checkpoints" / "cp.sqlite")},
            memory={"database_path": str(tmp_path / "sqlite" / "mem.sqlite")},
        )
        settings.ensure_data_directories()
        assert (tmp_path / "chroma").is_dir()
        assert (tmp_path / "checkpoints").is_dir()
        assert (tmp_path / "sqlite").is_dir()


@pytest.mark.unit
class TestLogging:
    def test_get_logger_returns_configured_logger(self) -> None:
        logger = get_logger("incident_agent.test")
        assert isinstance(logger, logging.Logger)
        assert logging.getLogger().handlers, "root logger should have a handler after configure_logging()"

    def test_configure_logging_is_idempotent(self) -> None:
        configure_logging()
        handler_count_after_first = len(logging.getLogger().handlers)
        configure_logging()
        assert len(logging.getLogger().handlers) == handler_count_after_first
