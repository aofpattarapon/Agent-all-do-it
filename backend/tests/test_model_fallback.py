"""Tests for the rate-limit backoff behavior in run_with_fallback.

Free-tier providers (Groq/Cerebras/Gemini) frequently return HTTP 429 with no
usable Retry-After header. The fallback layer must back off and retry the SAME
adapter a bounded number of times (queue the burst) before switching adapters,
rather than cascading every agent onto the scarce OpenRouter free pool at once.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import model_fallback
from app.services.runtime import groq_api, openrouter_api


def _agent() -> SimpleNamespace:
    """A groq-primary agent whose only fallback is the OpenRouter free pool."""
    return SimpleNamespace(
        runtime_kind="groq-api",
        model="llama-3.3-70b-versatile",
        max_tokens=2048,
        temperature=70,
        tools_config={
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ]
        },
    )


def _rate_limit_error() -> Exception:
    """A 429 with no ``response`` attribute → no usable Retry-After header."""
    return RuntimeError("rate limit exceeded (429 Too Many Requests)")


@pytest.mark.anyio
async def test_rate_limited_without_retry_after_backs_off_same_adapter_then_succeeds():
    groq_mock = AsyncMock(side_effect=[_rate_limit_error(), ("recovered", {"runtime": "groq-api"})])
    openrouter_mock = AsyncMock(return_value=("should-not-run", {"runtime": "openrouter-api"}))

    with (
        patch("asyncio.sleep", new=AsyncMock()) as sleep_mock,
        patch.object(groq_api, "run_agent", new=groq_mock),
        patch.object(openrouter_api, "run_agent", new=openrouter_mock),
    ):
        output, meta = await model_fallback.run_with_fallback(_agent(), prompt="hi")

    assert output == "recovered"
    assert meta["runtime"] == "groq-api"
    # Backed off and retried the SAME adapter — never reached the OpenRouter pool.
    assert groq_mock.await_count == 2
    openrouter_mock.assert_not_awaited()
    sleep_mock.assert_awaited()  # a backoff sleep happened


@pytest.mark.anyio
async def test_rate_limited_exhausts_backoff_then_falls_to_next_adapter():
    # Always 429 on groq → after _MAX_SAME_ADAPTER_RETRIES it moves to OpenRouter.
    groq_mock = AsyncMock(side_effect=_rate_limit_error())
    openrouter_mock = AsyncMock(return_value=("fallback-ok", {"runtime": "openrouter-api"}))

    with (
        patch("asyncio.sleep", new=AsyncMock()),
        patch.object(groq_api, "run_agent", new=groq_mock),
        patch.object(openrouter_api, "run_agent", new=openrouter_mock),
    ):
        output, meta = await model_fallback.run_with_fallback(_agent(), prompt="hi")

    assert output == "fallback-ok"
    assert meta["runtime"] == "openrouter-api"
    assert meta["fallback_used"] is True
    # 1 initial + _MAX_SAME_ADAPTER_RETRIES backoff attempts on the same adapter.
    assert groq_mock.await_count == model_fallback._MAX_SAME_ADAPTER_RETRIES + 1
    openrouter_mock.assert_awaited_once()
