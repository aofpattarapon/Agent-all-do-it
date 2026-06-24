"""Runtime profile definitions — source of truth for test / production mode.

A profile maps each agent role to:
  - runtime_kind  : which adapter to use as primary
  - model         : model identifier for that adapter
  - fallback_chain: ordered list of {runtime_kind, model} dicts to try on failure
  - gate_policy   : "continue" | "pause" — what to do when the agent fails critically
"""

from __future__ import annotations

import copy
from typing import Any, Literal, cast

ProfileName = Literal[
    "test",
    "test-2",
    "test-minimal-paid",
    "test-jam",
    "test-local-free-24x7-safe",
    "production",
]

VALID_PROFILES: tuple[ProfileName, ...] = (
    "test",
    "test-2",
    "test-minimal-paid",
    "test-jam",
    "test-local-free-24x7-safe",
    "production",
)

# ── Per-role profile definitions ──────────────────────────────────────────────

RUNTIME_PROFILES: dict[str, dict[str, dict[str, Any]]] = {
    # ── TEST MODE ─────────────────────────────────────────────────────────────
    # Free-tier only: groq-api (Llama) + openrouter-api (free models).
    # No paid API calls. Use for pipeline validation and prompt testing.
    "test": {
        # 24/7 free-tier profile. Primaries are SPREAD across provider pools
        # (cerebras-api, groq-api, google-ai-studio) by quality + context + RPD so
        # no single free pool is a bottleneck. openrouter/gpt-oss-120b:free (~50-1k
        # RPD) is demoted to LAST-RESORT fallback only. All gates = continue.
        "news_monitor": {
            # Long news + market text → Gemini 1M context.
            "runtime_kind": "google-ai-studio",
            "model": "gemini-2.0-flash",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "source_reliability": {
            # Light classification — speed over reasoning.
            "runtime_kind": "groq-api",
            "model": "llama-3.1-8b-instant",
            "fallback_chain": [
                {"runtime_kind": "cerebras-api", "model": "llama-3.1-8b"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "market_regime": {
            "runtime_kind": "cerebras-api",
            "model": "llama-3.3-70b",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "hawk_trend": {
            "runtime_kind": "cerebras-api",
            "model": "llama-3.3-70b",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "hawk_structure": {
            # Different pool from hawk_trend to avoid one-pool bursts on the vote.
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "cerebras-api", "model": "llama-3.3-70b"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "hawk_counter": {
            # Third distinct model/pool — diversity matters for the 2/3 vote gate.
            "runtime_kind": "cerebras-api",
            "model": "qwen-3-32b",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "gemma2-9b-it"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "sage": {
            # Top reasoning — Cerebras 70b primary, Gemini then Groq as quality fallbacks.
            "runtime_kind": "cerebras-api",
            "model": "llama-3.3-70b",
            "fallback_chain": [
                {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "trade_proposal": {
            # Structured proposal over long context → Gemini.
            "runtime_kind": "google-ai-studio",
            "model": "gemini-2.5-flash",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "execution": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "cerebras-api", "model": "llama-3.3-70b"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "position_monitor": {
            # Heaviest cron (every 5 min) — light task on the highest-RPD model.
            "runtime_kind": "groq-api",
            "model": "llama-3.1-8b-instant",
            "fallback_chain": [
                {"runtime_kind": "cerebras-api", "model": "llama-3.1-8b"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "trade_journal": {
            "runtime_kind": "groq-api",
            "model": "gemma2-9b-it",
            "fallback_chain": [
                {"runtime_kind": "groq-api", "model": "llama-3.1-8b-instant"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "continue",
        },
        "post_trade_review": {
            "runtime_kind": "cerebras-api",
            "model": "llama-3.3-70b",
            "fallback_chain": [
                {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
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
                {"runtime_kind": "google-ai-studio", "model": "gemini-2.0-flash"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {
                    "runtime_kind": "openrouter-api",
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                },
            ],
            "gate_policy": "continue",
        },
        "source_reliability": {
            "runtime_kind": "groq-api",
            "model": "llama-3.3-70b-versatile",
            "fallback_chain": [
                {"runtime_kind": "cerebras-api", "model": "llama-3.1-8b"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
                {
                    "runtime_kind": "openrouter-api",
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                },
            ],
            "gate_policy": "continue",
        },
        "market_regime": {
            "runtime_kind": "cerebras-api",
            "model": "llama-3.3-70b",
            "fallback_chain": [
                {"runtime_kind": "claude-cli", "model": "claude-sonnet-4-6"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
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
            # Every-5-min cron — keep off the scarce openrouter-free pool as primary.
            "runtime_kind": "groq-api",
            "model": "llama-3.1-8b-instant",
            "fallback_chain": [
                {"runtime_kind": "cerebras-api", "model": "llama-3.1-8b"},
                {"runtime_kind": "claude-cli", "model": "claude-haiku-4-5-20251001"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
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


def _with_overrides(
    base: dict[str, dict[str, Any]], overrides: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Return a deep copy of ``base`` with per-role fields shallow-merged from ``overrides``."""
    merged = copy.deepcopy(base)
    for role, patch in overrides.items():
        merged[role] = {**merged[role], **patch}
    return merged


# test-2: identical provider spread to `test`, but pause on the critical
# review/execution roles so unattended runs hold for inspection on failure.
RUNTIME_PROFILES["test-2"] = _with_overrides(
    RUNTIME_PROFILES["test"],
    {
        "sage": {"gate_policy": "pause"},
        "trade_proposal": {"gate_policy": "pause"},
        "execution": {"gate_policy": "pause"},
        "post_trade_review": {"gate_policy": "pause"},
    },
)

# test-jam: jam-resistant 24/7 profile. Same free provider spread as `test`
# (cerebras-api / groq-api / google-ai-studio primaries; openrouter gpt-oss-120b:free
# is last-resort only), with pause gates on the critical review/execution roles so
# unattended runs hold for inspection on failure. Pairs with the global backoff and
# Celery worker time-limit hardening so RPM bursts queue instead of cascading.
RUNTIME_PROFILES["test-jam"] = _with_overrides(
    RUNTIME_PROFILES["test"],
    {
        "sage": {"gate_policy": "pause"},
        "trade_proposal": {"gate_policy": "pause"},
        "execution": {"gate_policy": "pause"},
        "post_trade_review": {"gate_policy": "pause"},
    },
)

# test-minimal-paid: same free spread, but the highest-stakes reasoning roles use
# Claude (Anthropic API). Their fallback chains drop back to the free providers.
RUNTIME_PROFILES["test-minimal-paid"] = _with_overrides(
    RUNTIME_PROFILES["test"],
    {
        "sage": {
            "runtime_kind": "anthropic-api",
            "model": "claude-opus-4-8",
            "fallback_chain": [
                {"runtime_kind": "cerebras-api", "model": "llama-3.3-70b"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "pause",
        },
        "trade_proposal": {
            "runtime_kind": "anthropic-api",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "pause",
        },
        "execution": {"gate_policy": "pause"},
        "post_trade_review": {
            "runtime_kind": "anthropic-api",
            "model": "claude-sonnet-4-6",
            "fallback_chain": [
                {"runtime_kind": "cerebras-api", "model": "llama-3.3-70b"},
                {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
                {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            ],
            "gate_policy": "pause",
        },
    },
)

# test-local-free-24x7-safe: experimental Ollama-primary 24/7 profile.
# Local models carry the critical path; free cloud providers are explicit fallbacks.
RUNTIME_PROFILES["test-local-free-24x7-safe"] = {
    "news_monitor": {
        "runtime_kind": "ollama",
        "model": "gemma3:12b",
        "fallback_chain": [
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.0-flash"},
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
        ],
        "gate_policy": "continue",
    },
    "source_reliability": {
        "runtime_kind": "ollama",
        "model": "qwen3:8b",
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "llama-3.1-8b-instant"},
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.0-flash"},
        ],
        "gate_policy": "continue",
    },
    "market_regime": {
        "runtime_kind": "ollama",
        "model": "qwen3:14b",
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
        ],
        "gate_policy": "continue",
    },
    "hawk_trend": {
        "runtime_kind": "ollama",
        "model": "qwen3:14b",
        "temperature": 0,
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
        ],
        "gate_policy": "continue",
    },
    "hawk_structure": {
        "runtime_kind": "ollama",
        "model": "gemma3:12b",
        "temperature": 0,
        "fallback_chain": [
            {"runtime_kind": "ollama", "model": "qwen3:14b"},
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
        ],
        "gate_policy": "continue",
    },
    "hawk_counter": {
        "runtime_kind": "ollama",
        "model": "qwen3:14b",
        "temperature": 0,
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
        ],
        "gate_policy": "continue",
    },
    "sage": {
        "runtime_kind": "ollama",
        "model": "qwen3:14b",
        "temperature": 0,
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
        ],
        "gate_policy": "pause",
    },
    "trade_proposal": {
        "runtime_kind": "ollama",
        "model": "qwen3:14b",
        "temperature": 0,
        "fallback_chain": [
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
        ],
        "gate_policy": "pause",
    },
    "execution": {
        "runtime_kind": "ollama",
        "model": "qwen3:8b",
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
        ],
        "gate_policy": "pause",
    },
    "position_monitor": {
        "runtime_kind": "ollama",
        "model": "qwen3:8b",
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "llama-3.1-8b-instant"},
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.0-flash"},
        ],
        "gate_policy": "continue",
    },
    "trade_journal": {
        "runtime_kind": "ollama",
        "model": "gemma3:12b",
        "fallback_chain": [
            {"runtime_kind": "ollama", "model": "qwen3:8b"},
            {"runtime_kind": "groq-api", "model": "llama-3.1-8b-instant"},
        ],
        "gate_policy": "continue",
    },
    "post_trade_review": {
        "runtime_kind": "ollama",
        "model": "qwen3:14b",
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.5-flash"},
        ],
        "gate_policy": "pause",
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
) -> Literal[
    "test",
    "test-2",
    "test-minimal-paid",
    "test-jam",
    "test-local-free-24x7-safe",
    "production",
    "custom",
]:
    """Return whether an agent's current runtime matches the given profile, or 'custom'."""
    policy = get_role_policy(profile_name, role)
    if policy is None:
        return "custom"
    if policy["runtime_kind"] == runtime_kind and policy["model"] == model:
        return cast(ProfileName, profile_name)
    return "custom"
