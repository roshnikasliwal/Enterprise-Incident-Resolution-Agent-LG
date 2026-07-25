"""LLM client factory -- Strategy pattern for provider selection, with
built-in fallback chaining and retry.

Why this exists
----------------
The requirement is "Anthropic first, fallback OpenAI/Azure OpenAI, easy
to switch." Concretely, that means three things have to compose cleanly:

1. **Provider selection is a config value, not an `if/elif` scattered
   through agent code** -- each provider's chat-model construction is
   its own small `_ProviderStrategy`, keyed by `settings.llm.
   primary_provider` / `fallback_providers` (see `config/settings.py`).
2. **Fallback is a real runtime behavior, not just "you could switch
   the config"** -- if the primary provider's call fails (auth error,
   rate limit, timeout), the *same request* should be retried against
   the next configured provider automatically, mid-run. LangChain's
   `Runnable.with_fallbacks()` does exactly this at the chain level, so
   we compose each provider's *structured-output* runnable (not just
   the bare chat model) into one fallback chain -- a validation failure
   in provider A's structured output also triggers provider B, not just
   a raw API error.
3. **Only providers with credentials configured are wired in.** A
   fallback pointing at a provider with no API key would just fail
   immediately and waste the fallback attempt; we filter those out up
   front and raise a clear, actionable error if *no* provider is usable
   at all, rather than letting the graph fail confusingly three nodes
   later.
"""

from __future__ import annotations

from typing import Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from incident_agent.config.settings import LLMProvider, Settings, get_settings


class LLMProviderNotConfiguredError(RuntimeError):
    """Raised when none of the configured providers (primary + fallbacks)
    have credentials present -- a startup-time configuration problem, not a
    transient runtime one."""


class _ProviderStrategy(Protocol):
    def build(self, settings: Settings) -> BaseChatModel: ...

    def is_configured(self, settings: Settings) -> bool: ...


class _AnthropicStrategy:
    def build(self, settings: Settings) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic.model,
            api_key=settings.anthropic.api_key,
            temperature=settings.llm.temperature,
            max_tokens=settings.llm.max_tokens,
            timeout=settings.llm.request_timeout_seconds,
        )

    def is_configured(self, settings: Settings) -> bool:
        return settings.anthropic.api_key is not None


class _OpenAIStrategy:
    def build(self, settings: Settings) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai.model,
            api_key=settings.openai.api_key,
            temperature=settings.llm.temperature,
            max_tokens=settings.llm.max_tokens,
            timeout=settings.llm.request_timeout_seconds,
        )

    def is_configured(self, settings: Settings) -> bool:
        return settings.openai.api_key is not None


class _AzureOpenAIStrategy:
    def build(self, settings: Settings) -> BaseChatModel:
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_endpoint=settings.azure_openai.endpoint,
            azure_deployment=settings.azure_openai.deployment,
            api_version=settings.azure_openai.api_version,
            api_key=settings.azure_openai.api_key,
            temperature=settings.llm.temperature,
            max_tokens=settings.llm.max_tokens,
            timeout=settings.llm.request_timeout_seconds,
        )

    def is_configured(self, settings: Settings) -> bool:
        azure = settings.azure_openai
        return bool(azure.api_key and azure.endpoint and azure.deployment)


_PROVIDER_STRATEGIES: dict[LLMProvider, _ProviderStrategy] = {
    "anthropic": _AnthropicStrategy(),
    "openai": _OpenAIStrategy(),
    "azure_openai": _AzureOpenAIStrategy(),
}


class LLMClientFactory:
    """Builds a fallback-chained, retrying, structured-output `Runnable` for
    a given Pydantic output schema. One factory instance is reused across
    every agent -- construction is cheap and the factory itself is stateless
    beyond holding a `Settings` reference.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _configured_provider_order(self) -> list[LLMProvider]:
        candidates = [self._settings.llm.primary_provider, *self._settings.llm.fallback_providers]
        return [p for p in candidates if _PROVIDER_STRATEGIES[p].is_configured(self._settings)]

    def build_structured_llm(self, output_schema: type[BaseModel]) -> Runnable:
        """Return `prompt`-ready `Runnable` that, given messages, produces a
        validated instance of `output_schema` -- trying the primary provider
        first, falling back through the remaining configured providers on
        failure, with exponential-backoff retry wrapping the whole chain.
        """
        providers = self._configured_provider_order()
        if not providers:
            raise LLMProviderNotConfiguredError(
                "No LLM provider is configured with credentials. Set at least "
                "ANTHROPIC__API_KEY (primary) in your .env -- see .env.example."
            )

        structured_runnables = [
            _PROVIDER_STRATEGIES[provider].build(self._settings).with_structured_output(output_schema)
            for provider in providers
        ]
        primary, *fallbacks = structured_runnables
        chain: Runnable = primary.with_fallbacks(fallbacks) if fallbacks else primary
        return chain.with_retry(
            stop_after_attempt=self._settings.llm.max_retries + 1,
            wait_exponential_jitter=True,
        )

    def build_chat_model(self, provider: LLMProvider | None = None) -> BaseChatModel:
        """Return a bare (non-structured-output) chat model for the given
        provider, or the primary provider if unspecified. Used by agents that
        need raw text generation rather than a Pydantic-schema response."""
        provider = provider or self._settings.llm.primary_provider
        strategy = _PROVIDER_STRATEGIES[provider]
        if not strategy.is_configured(self._settings):
            raise LLMProviderNotConfiguredError(f"Provider '{provider}' has no credentials configured.")
        return strategy.build(self._settings)
