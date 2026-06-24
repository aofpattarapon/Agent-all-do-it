from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.core.runtime_catalog import (
    DEFAULT_MODEL_BY_RUNTIME,
    RUNTIME_MODEL_OPTIONS,
    default_model_for_runtime,
    normalize_runtime_model_pair,
)
from app.schemas.agent_config import AgentConfigCreate, AgentConfigUpdate
from app.services.agent_config import AgentConfigService, merge_runtime_tools_config


def test_normalize_runtime_model_pair_accepts_valid_combination():
    runtime, model = normalize_runtime_model_pair("codex-cli", "o4-mini")
    assert runtime == "codex-cli"
    assert model == "o4-mini"


def test_normalize_runtime_model_pair_defaults_cli_model():
    runtime, model = normalize_runtime_model_pair("codex-cli", "")
    assert runtime == "codex-cli"
    assert model == default_model_for_runtime("codex-cli")


def test_normalize_runtime_model_pair_rejects_invalid_combination():
    with pytest.raises(ValidationError):
        normalize_runtime_model_pair("codex-cli", "claude-haiku-4-5-20251001")


def test_normalize_runtime_model_pair_accepts_cerebras_models():
    runtime, model = normalize_runtime_model_pair("cerebras-api", "llama-3.3-70b")
    assert runtime == "cerebras-api"
    assert model == "llama-3.3-70b"


def test_normalize_runtime_model_pair_accepts_google_ai_studio_models():
    runtime, model = normalize_runtime_model_pair("google-ai-studio", "gemini-2.0-flash")
    assert runtime == "google-ai-studio"
    assert model == "gemini-2.0-flash"


def test_openrouter_free_model_catalog_phase_b_cleanup():
    """Lock Phase B catalog cleanup: removed stale IDs, verified replacement, default valid."""
    options = RUNTIME_MODEL_OPTIONS["openrouter-api"]
    assert "moonshotai/kimi-k2.6:free" not in options
    assert "google/gemma-3-27b-it:free" not in options
    assert "google/gemma-4-31b-it:free" in options
    default = DEFAULT_MODEL_BY_RUNTIME["openrouter-api"]
    assert default in options


@pytest.mark.parametrize("model", ["qwen3:8b", "qwen3:14b", "gemma3:12b"])
def test_normalize_runtime_model_pair_accepts_new_ollama_models(model: str):
    runtime, normalized_model = normalize_runtime_model_pair("ollama", model)
    assert runtime == "ollama"
    assert normalized_model == model


def test_normalize_runtime_model_pair_defaults_cerebras_model():
    runtime, model = normalize_runtime_model_pair("cerebras-api", "")
    assert runtime == "cerebras-api"
    assert model == default_model_for_runtime("cerebras-api") == "llama-3.3-70b"


def test_normalize_runtime_model_pair_rejects_bad_cerebras_model():
    with pytest.raises(ValidationError):
        normalize_runtime_model_pair("cerebras-api", "gemini-2.0-flash")


def test_merge_runtime_tools_config_sets_runtime_backend_and_model():
    merged = merge_runtime_tools_config(
        {"custom": "value", "runtime_kind": "groq-api"},
        runtime_kind="kimi-cli",
        model="kimi-k2.6",
    )
    assert merged["custom"] == "value"
    assert merged["runtime_kind"] == "kimi-cli"
    assert merged["ai_backend"] == "kimi-cli"
    assert merged["model"] == "kimi-k2.6"


@pytest.mark.anyio
async def test_agent_config_service_create_rejects_invalid_runtime_model_pair():
    svc = AgentConfigService(AsyncMock())
    with pytest.raises(ValidationError):
        await svc.create(
            uuid4(),
            AgentConfigCreate(
                name="Bad Agent",
                role="tester",
                system_prompt="test",
                runtime_kind="codex-cli",
                model="claude-haiku-4-5-20251001",
            ),
        )


@pytest.mark.anyio
async def test_agent_config_service_update_normalizes_tools_config_runtime():
    db = AsyncMock()
    svc = AgentConfigService(db)
    agent_id = uuid4()
    project_id = uuid4()
    existing = SimpleNamespace(
        id=agent_id,
        project_id=project_id,
        runtime_kind="claude-cli",
        model="",
        tools_config={"runtime_kind": "claude-cli", "ai_backend": "claude-cli"},
    )

    with (
        patch.object(svc, "get", new=AsyncMock(return_value=existing)),
        patch(
            "app.services.agent_config.agent_config_repo.update",
            new=AsyncMock(return_value=existing),
        ) as update_mock,
    ):
        await svc.update(
            agent_id,
            project_id,
            AgentConfigUpdate(runtime_kind="codex-cli", model="o4-mini"),
        )

    payload = update_mock.await_args.kwargs["update_data"]
    assert payload["runtime_kind"] == "codex-cli"
    assert payload["model"] == "o4-mini"
    assert payload["tools_config"]["runtime_kind"] == "codex-cli"
    assert payload["tools_config"]["ai_backend"] == "codex-cli"
    assert payload["tools_config"]["model"] == "o4-mini"
