"""Runtime adapters — execute an agent against a backend selected by ``runtime_kind``.

Public API:
    run_agent(agent, prompt, system_prompt) -> (output_text, metadata)
    healthcheck_all() -> list[dict]
    healthcheck(kind) -> dict

Each adapter module exposes ``run_agent(*, prompt, system_prompt, model, max_tokens,
temperature)`` and ``healthcheck()``. CLI adapters (claude-cli/codex-cli) work WITHOUT
an API key by shelling out to the locally installed binary.
"""

from typing import TYPE_CHECKING

from app.services.runtime import (
    anthropic_api,
    claude_cli,
    claude_cli_work,
    codex_cli,
    groq_api,
    kimi_api,
    kimi_cli,
    ollama_sdk,
    openai_api,
    openrouter_api,
)

if TYPE_CHECKING:
    from app.db.models.project import AgentConfig

# runtime_kind → adapter module
_ADAPTERS = {
    "claude-cli": claude_cli,
    "claude-cli-work": claude_cli_work,
    "codex-cli": codex_cli,
    "kimi-cli": kimi_cli,
    "kimi-api": kimi_api,
    "groq-api": groq_api,
    "anthropic-api": anthropic_api,
    "openai-api": openai_api,
    "ollama": ollama_sdk,
    "openrouter-api": openrouter_api,
}

DEFAULT_RUNTIME = "anthropic-api"


async def run_agent(
    agent: "AgentConfig",
    prompt: str,
    system_prompt: str = "",
) -> tuple[str, dict]:
    """Dispatch an agent run to the adapter matching ``agent.runtime_kind``.

    Returns (output_text, metadata). ``metadata`` always contains ``runtime`` and,
    where the backend exposes it, ``tokens_used``.
    """
    kind = (getattr(agent, "runtime_kind", "") or DEFAULT_RUNTIME).strip()
    adapter = _ADAPTERS.get(kind, anthropic_api)

    model = getattr(agent, "model", "") or ""
    max_tokens = getattr(agent, "max_tokens", None) or 2048
    # temperature is stored x100 (0-200) on AgentConfig — normalise to a float.
    raw_temp = getattr(agent, "temperature", None)
    temperature = (raw_temp / 100.0) if isinstance(raw_temp, (int, float)) else 0.7

    return await adapter.run_agent(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def healthcheck(kind: str) -> dict:
    """Run the healthcheck for a single runtime kind."""
    adapter = _ADAPTERS.get(kind)
    if adapter is None:
        return {"kind": kind, "available": False, "detail": "unknown runtime kind"}
    return adapter.healthcheck()


def healthcheck_all() -> list[dict]:
    """Run every adapter's healthcheck."""
    return [adapter.healthcheck() for adapter in _ADAPTERS.values()]


__all__ = ["healthcheck", "healthcheck_all", "run_agent"]
