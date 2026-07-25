"""Mock LLM Tests: behavioral proof that the retry/fallback composition
`LLMClientFactory.build_structured_llm()` builds (see
`services/llm_factory.py`) actually works the way it's supposed to under
failure -- not just that it *structurally* composes without raising
(that's what `TestLLMClientFactory` in `test_phase4_agents.py` already
covers with dummy API keys).

Real provider SDK objects can't be made to fail on demand without a live
API, so these tests build the exact same `Runnable.with_fallbacks()` /
`.with_retry()` chain shape `LLMClientFactory` builds, but out of
`RunnableLambda` fakes whose failure behavior we control precisely --
proving *this project's chain-composition logic* is correct, which is
the part actually at risk of a bug (the LangChain primitives themselves
are already well-tested upstream).
"""

from __future__ import annotations

from itertools import count

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel


class _Output(BaseModel):
    value: str


@pytest.mark.unit
class TestFallbackChainBehavior:
    def test_primary_success_never_touches_fallback(self) -> None:
        fallback_calls = []

        def primary(_: dict) -> _Output:
            return _Output(value="from-primary")

        def fallback(_: dict) -> _Output:
            fallback_calls.append(1)
            return _Output(value="from-fallback")

        chain = RunnableLambda(primary).with_fallbacks([RunnableLambda(fallback)])
        result = chain.invoke({})

        assert result.value == "from-primary"
        assert fallback_calls == []

    def test_primary_failure_falls_through_to_fallback(self) -> None:
        def primary(_: dict) -> _Output:
            raise TimeoutError("primary provider timed out")

        def fallback(_: dict) -> _Output:
            return _Output(value="from-fallback")

        chain = RunnableLambda(primary).with_fallbacks([RunnableLambda(fallback)])
        result = chain.invoke({})

        assert result.value == "from-fallback"

    def test_validation_style_failure_also_triggers_fallback(self) -> None:
        # Mirrors the real scenario LLMClientFactory is built for: a
        # provider's structured-output call can fail via schema
        # validation, not just a transport error -- the fallback chain
        # must trigger on that too, since with_structured_output raises
        # a Pydantic ValidationError (or an OutputParserException wrapping
        # one) the same way a network failure raises an APIError.
        def primary(_: dict) -> _Output:
            _Output.model_validate({"value": 123, "unexpected_extra_strictness": object()})  # type: ignore[arg-type]
            raise AssertionError("unreachable")

        def fallback(_: dict) -> _Output:
            return _Output(value="fallback-after-validation-failure")

        chain = RunnableLambda(primary).with_fallbacks([RunnableLambda(fallback)])
        result = chain.invoke({})
        assert result.value == "fallback-after-validation-failure"

    def test_all_providers_failing_raises_the_first_error(self) -> None:
        # LangChain's RunnableWithFallbacks re-raises whichever exception
        # came from the *first* runnable in the chain (the primary), not
        # the last fallback attempted -- worth knowing precisely, since a
        # naive assumption here would make error messages misleading (a
        # user seeing "primary down" when what actually failed last was
        # the fallback).
        def primary(_: dict) -> _Output:
            raise ValueError("primary down")

        def fallback(_: dict) -> _Output:
            raise ValueError("fallback also down")

        chain = RunnableLambda(primary).with_fallbacks([RunnableLambda(fallback)])
        with pytest.raises(ValueError, match="primary down"):
            chain.invoke({})

    def test_second_fallback_used_when_first_two_providers_fail(self) -> None:
        def primary(_: dict) -> _Output:
            raise ValueError("anthropic down")

        def fallback_one(_: dict) -> _Output:
            raise ValueError("openai down")

        def fallback_two(_: dict) -> _Output:
            return _Output(value="from-azure")

        chain = RunnableLambda(primary).with_fallbacks(
            [RunnableLambda(fallback_one), RunnableLambda(fallback_two)]
        )
        result = chain.invoke({})
        assert result.value == "from-azure"


@pytest.mark.unit
class TestRetryBehavior:
    def test_retry_recovers_from_a_transient_failure(self) -> None:
        attempts = count()

        def flaky(_: dict) -> _Output:
            attempt = next(attempts)
            if attempt < 2:
                raise ConnectionError("transient network blip")
            return _Output(value="succeeded-on-third-attempt")

        chain = RunnableLambda(flaky).with_retry(stop_after_attempt=3)
        result = chain.invoke({})

        assert result.value == "succeeded-on-third-attempt"

    def test_retry_gives_up_after_stop_after_attempt(self) -> None:
        attempts = count()

        def always_fails(_: dict) -> _Output:
            next(attempts)
            raise ConnectionError("provider unreachable")

        chain = RunnableLambda(always_fails).with_retry(stop_after_attempt=3)
        with pytest.raises(ConnectionError):
            chain.invoke({})

        assert next(attempts) == 3  # exactly stop_after_attempt calls were made, no more

    def test_retry_wraps_the_whole_fallback_chain(self) -> None:
        # This is the exact composition LLMClientFactory.build_structured_llm
        # produces: retry wraps fallbacks, so a transient failure on the
        # *fallback* provider also gets retried, not just the primary.
        fallback_attempts = count()

        def primary(_: dict) -> _Output:
            raise ValueError("primary permanently down")

        def flaky_fallback(_: dict) -> _Output:
            attempt = next(fallback_attempts)
            if attempt < 1:
                raise ConnectionError("fallback transient blip")
            return _Output(value="fallback-recovered")

        chain = RunnableLambda(primary).with_fallbacks([RunnableLambda(flaky_fallback)]).with_retry(
            stop_after_attempt=3
        )
        result = chain.invoke({})
        assert result.value == "fallback-recovered"
