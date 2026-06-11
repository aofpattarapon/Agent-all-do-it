"""Runtime profile definitions — source of truth for test / production mode.

A profile maps each agent role to:
  - runtime_kind  : which adapter to use as primary
  - model         : model identifier for that adapter
  - fallback_chain: ordered list of {runtime_kind, model} dicts to try on failure
  - gate_policy   : "continue" | "pause" — what to do when the agent fails critically
"""

from __future__ import annotations

from typing import Any, Literal

ProfileName = Literal["test", "production"]

VALID_PROFILES: tuple[ProfileName, ...] = ("test", "production")

# ── Per-role profile definitions ──────────────────────────────────────────────

RUNTIME_PROFILES: dict[str, dict[str, dict[str, Any]]] = {
    "test": {
        "news_monitor": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "source_reliability": {
            "runtime_kind": "openrouter-api",
            "model": "meta-llama/llama-3.3-70b-instruct:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "market_regime": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "hawk_trend": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "hawk_structure": {
            "runtime_kind": "openrouter-api",
            "model": "meta-llama/llama-3.3-70b-instruct:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "hawk_counter": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "sage": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "trade_proposal": {
            "runtime_kind": "openrouter-api",
            "model": "meta-llama/llama-3.3-70b-instruct:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "execution": {
            "runtime_kind": "groq-api",
            "model": "llama-3.1-8b-instant",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "position_monitor": {
            "runtime_kind": "groq-api",
            "model": "llama-3.1-8b-instant",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "trade_journal": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
        "post_trade_review": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
            ],
            "gate_policy": "continue",
        },
    },
    "production": {
        "news_monitor": {
            "runtime_kind": "kimi-cli",
            "model": "kimi-k2.6",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
            ],
            "gate_policy": "continue",
        },
        "source_reliability": {
            "runtime_kind": "claude-cli",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "pause",
        },
        "market_regime": {
            "runtime_kind": "kimi-cli",
            "model": "kimi-k2.6",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
            ],
            "gate_policy": "continue",
        },
        "hawk_trend": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
            ],
            "gate_policy": "continue",
        },
        "hawk_structure": {
            "runtime_kind": "claude-cli",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "continue",
        },
        "hawk_counter": {
            "runtime_kind": "kimi-cli",
            "model": "kimi-k2.6",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
            ],
            "gate_policy": "continue",
        },
        "sage": {
            "runtime_kind": "claude-cli",
            "model": "claude-opus-4-8",
            "fallback_chain": [
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "pause",
        },
        "trade_proposal": {
            "runtime_kind": "claude-cli",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "pause",
        },
        "execution": {
            "runtime_kind": "groq-api",
            "model": "llama-3.1-8b-instant",
            "fallback_chain": [
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
            ],
            "gate_policy": "pause",
        },
        "position_monitor": {
            "runtime_kind": "groq-api",
            "model": "llama-3.1-8b-instant",
            "fallback_chain": [
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
            ],
            "gate_policy": "continue",
        },
        "trade_journal": {
            "runtime_kind": "kimi-cli",
            "model": "kimi-k2.6",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
            ],
            "gate_policy": "continue",
        },
        "post_trade_review": {
            "runtime_kind": "claude-cli",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "kimi-cli", "model": "kimi-k2.6"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "pause",
        },
    },
}


def get_profile(profile_name: str) -> dict[str, dict[str, Any]]:
    """Return role → policy mapping for the given profile name.

    Raises ValueError for unknown profile names.
    """
    if profile_name not in RUNTIME_PROFILES:
        raise ValueError(
            f"Unknown profile '{profile_name}'. Valid profiles: {', '.join(VALID_PROFILES)}"
        )
    return RUNTIME_PROFILES[profile_name]


def get_role_policy(profile_name: str, role: str) -> dict[str, Any] | None:
    """Return the policy for a specific role within a profile, or None if not mapped."""
    profile = get_profile(profile_name)
    return profile.get(role)


def classify_agent_profile(
    profile_name: str, runtime_kind: str, model: str, role: str
) -> Literal["test", "production", "custom"]:
    """Return whether an agent's current runtime matches the given profile, or 'custom'."""
    policy = get_role_policy(profile_name, role)
    if policy is None:
        return "custom"
    if policy["runtime_kind"] == runtime_kind and policy["model"] == model:
        return profile_name  # type: ignore[return-value]
    return "custom"
