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
    # ── TEST MODE ─────────────────────────────────────────────────────────────
    # Free-tier only: groq-api (Llama) + openrouter-api (free models).
    # No paid API calls. Use for pipeline validation and prompt testing.
    "test": {
        # All agents: primary = openrouter/gpt-oss-120b:free (free, no cost).
        # fb1 = groq/llama-3.3-70b-versatile, fb2 = openrouter/llama-3.3-70b:free.
        # All gates = continue — run overnight without human intervention.
        "news_monitor": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "source_reliability": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "market_regime": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "hawk_trend": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "hawk_structure": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "hawk_counter": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "sage": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "trade_proposal": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "execution": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "position_monitor": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "trade_journal": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "post_trade_review": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
    },
    # ── PRODUCTION MODE ───────────────────────────────────────────────────────
    # Claude agents use claude-cli (CLI bridge) — models unchanged.
    # codex-cli used for Execution Agent (structured JSON + reasoning strength).
    # Critical gates (SAGE, Trade Proposal, Post-Trade Review) use pause policy.
    "production": {
        "news_monitor": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "source_reliability": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
            ],
            "gate_policy": "continue",
        },
        "market_regime": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "continue",
        },
        "hawk_trend": {
            "runtime_kind": "claude-cli",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "continue",
        },
        "hawk_structure": {
            "runtime_kind": "claude-cli",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "continue",
        },
        "hawk_counter": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {"runtime_kind": "claude-cli", "model": "claude-haiku-4-5-20251001"},
            ],
            "gate_policy": "continue",
        },
        "sage": {
            "runtime_kind": "claude-cli",
            "model": "claude-opus-4-8",
            "fallback_chain": [
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "pause",
        },
        "trade_proposal": {
            "runtime_kind": "claude-cli",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "pause",
        },
        "execution": {
            "runtime_kind": "codex-cli",
            "model": "o4-mini",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {"runtime_kind": "claude-cli", "model": "claude-haiku-4-5-20251001"},
            ],
            "gate_policy": "pause",
        },
        "position_monitor": {
            "runtime_kind": "openrouter-api",
            "model": "openai/gpt-oss-120b:free",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.1-8b-instant"},
                {"runtime_kind": "claude-cli", "model": "claude-haiku-4-5-20251001"},
            ],
            "gate_policy": "continue",
        },
        "trade_journal": {
            "runtime_kind": "claude-cli",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            ],
            "gate_policy": "continue",
        },
        "post_trade_review": {
            "runtime_kind": "claude-cli",
            "model": "claude-opus-4-8",
            "fallback_chain": [
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
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
