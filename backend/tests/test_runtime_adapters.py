"""Tests for the Cerebras and Google AI Studio runtime adapters.

Both are OpenAI-compatible, so we patch ``openai.AsyncOpenAI`` and assert the
adapter targets the right base URL, returns ``(text, meta)`` with the expected
runtime tag, and reports availability via ``healthcheck``.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.runtime import cerebras_api, google_ai_api, groq_api


def _fake_response(text: str = "ok") -> SimpleNamespace:
    """Build a minimal OpenAI-style chat completion response."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    return SimpleNamespace(choices=[choice], usage=usage)


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_fake_response())
    return client


class TestCerebrasAdapter:
    @pytest.mark.anyio
    async def test_run_agent_targets_cerebras_base_url(self):
        with patch("openai.AsyncOpenAI") as mock_ctor:
            mock_ctor.return_value = _mock_client()
            text, meta = await cerebras_api.run_agent(
                prompt="hi", model="llama-3.3-70b", api_key="key"
            )
        assert text == "ok"
        assert meta["runtime"] == "cerebras-api"
        assert meta["model"] == "llama-3.3-70b"
        assert meta["tokens_used"] == 15
        assert mock_ctor.call_args.kwargs["base_url"] == cerebras_api.CEREBRAS_BASE_URL

    @pytest.mark.anyio
    async def test_run_agent_uses_default_model_when_unset(self):
        with patch("openai.AsyncOpenAI") as mock_ctor:
            mock_ctor.return_value = _mock_client()
            _text, meta = await cerebras_api.run_agent(prompt="hi", api_key="key")
        assert meta["model"] == cerebras_api.DEFAULT_MODEL

    @pytest.mark.anyio
    async def test_run_agent_raises_without_key(self):
        with (
            patch.object(cerebras_api.settings, "CEREBRAS_API_KEY", "", create=True),
            pytest.raises(RuntimeError, match="CEREBRAS_API_KEY"),
        ):
            await cerebras_api.run_agent(prompt="hi")

    def test_healthcheck_reflects_key_presence(self):
        with patch.object(cerebras_api.settings, "CEREBRAS_API_KEY", "key", create=True):
            result = cerebras_api.healthcheck()
        assert result["kind"] == "cerebras-api"
        assert result["available"] is True


class TestGoogleAIStudioAdapter:
    @pytest.mark.anyio
    async def test_run_agent_targets_google_base_url(self):
        with patch("openai.AsyncOpenAI") as mock_ctor:
            mock_ctor.return_value = _mock_client()
            text, meta = await google_ai_api.run_agent(
                prompt="hi", model="gemini-2.0-flash", api_key="key"
            )
        assert text == "ok"
        assert meta["runtime"] == "google-ai-studio"
        assert meta["model"] == "gemini-2.0-flash"
        assert mock_ctor.call_args.kwargs["base_url"] == google_ai_api.GOOGLE_AI_BASE_URL

    @pytest.mark.anyio
    async def test_run_agent_uses_default_model_when_unset(self):
        with patch("openai.AsyncOpenAI") as mock_ctor:
            mock_ctor.return_value = _mock_client()
            _text, meta = await google_ai_api.run_agent(prompt="hi", api_key="key")
        assert meta["model"] == google_ai_api.DEFAULT_MODEL == "gemini-2.0-flash"

    @pytest.mark.anyio
    async def test_run_agent_raises_without_key(self):
        with (
            patch.object(google_ai_api.settings, "GOOGLE_API_KEY", "", create=True),
            pytest.raises(RuntimeError, match="GOOGLE_API_KEY"),
        ):
            await google_ai_api.run_agent(prompt="hi")

    def test_healthcheck_reflects_key_presence(self):
        with patch.object(google_ai_api.settings, "GOOGLE_API_KEY", "key", create=True):
            result = google_ai_api.healthcheck()
        assert result["kind"] == "google-ai-studio"
        assert result["available"] is True


class TestAdapterRegistration:
    def test_both_adapters_registered_in_dispatch_table(self):
        from app.services import runtime as runtime_mod

        assert runtime_mod._ADAPTERS["cerebras-api"] is cerebras_api
        assert runtime_mod._ADAPTERS["google-ai-studio"] is google_ai_api


class TestGroqAdapterRetries:
    """Groq must disable the OpenAI SDK's internal retries so run_with_fallback
    owns retry/backoff — otherwise a 429 is silently multiplied by hidden retries."""

    @pytest.mark.anyio
    async def test_run_agent_builds_client_with_max_retries_zero(self):
        with patch("openai.AsyncOpenAI") as mock_ctor:
            mock_ctor.return_value = _mock_client()
            await groq_api.run_agent(prompt="hi", api_key="key")
        assert mock_ctor.call_args.kwargs["max_retries"] == 0
        assert mock_ctor.call_args.kwargs["base_url"] == groq_api.GROQ_BASE_URL
