"""Tests for the four-profile runtime profile system."""

from __future__ import annotations

import pytest

from app.core.runtime_catalog import is_valid_runtime_model_pair
from app.services.agent_config import merge_runtime_tools_config
from app.services.runtime_profiles import (
    VALID_PROFILES,
    classify_agent_profile,
    get_profile,
    get_role_policy,
)

EXPECTED_ROLES = {
    "news_monitor",
    "source_reliability",
    "market_regime",
    "hawk_trend",
    "hawk_structure",
    "hawk_counter",
    "sage",
    "trade_proposal",
    "execution",
    "position_monitor",
    "trade_journal",
    "post_trade_review",
}

EXPECTED_TEST_PROFILE = {
    "news_monitor": {
        "runtime_kind": "google-ai-studio",
        "model": "gemini-2.0-flash",
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "llama-3.3-70b-versatile"},
            {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
        ],
        "gate_policy": "continue",
    },
    "source_reliability": {
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
        "runtime_kind": "groq-api",
        "model": "llama-3.3-70b-versatile",
        "fallback_chain": [
            {"runtime_kind": "cerebras-api", "model": "llama-3.3-70b"},
            {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
        ],
        "gate_policy": "continue",
    },
    "hawk_counter": {
        "runtime_kind": "cerebras-api",
        "model": "qwen-3-32b",
        "fallback_chain": [
            {"runtime_kind": "groq-api", "model": "gemma2-9b-it"},
            {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
        ],
        "gate_policy": "continue",
    },
    "sage": {
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
}

EXPECTED_PRODUCTION_PROFILE = {
    "news_monitor": {
        "runtime_kind": "groq-api",
        "model": "llama-3.3-70b-versatile",
        "fallback_chain": [
            {"runtime_kind": "google-ai-studio", "model": "gemini-2.0-flash"},
            {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
        ],
        "gate_policy": "continue",
    },
    "source_reliability": {
        "runtime_kind": "groq-api",
        "model": "llama-3.3-70b-versatile",
        "fallback_chain": [
            {"runtime_kind": "cerebras-api", "model": "llama-3.1-8b"},
            {"runtime_kind": "openrouter-api", "model": "openai/gpt-oss-120b:free"},
            {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"},
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
}

EXPECTED_LOCAL_FREE_24X7_PROFILE = {
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


class TestGetProfile:
    def test_raises_for_unknown_profile(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            get_profile("staging")

    def test_all_valid_profiles_resolvable(self):
        assert VALID_PROFILES == (
            "test",
            "test-2",
            "test-minimal-paid",
            "test-jam",
            "test-local-free-24x7-safe",
            "production",
        )
        for name in VALID_PROFILES:
            assert isinstance(get_profile(name), dict)


class TestProfileCompleteness:
    @pytest.mark.parametrize("profile_name", VALID_PROFILES)
    def test_all_12_roles_present(self, profile_name: str):
        assert set(get_profile(profile_name).keys()) == EXPECTED_ROLES

    @pytest.mark.parametrize("profile_name", VALID_PROFILES)
    def test_each_role_has_required_fields(self, profile_name: str):
        required = {"runtime_kind", "model", "fallback_chain", "gate_policy"}
        for role, policy in get_profile(profile_name).items():
            assert required.issubset(set(policy.keys())), role

    @pytest.mark.parametrize("profile_name", VALID_PROFILES)
    def test_fallback_chain_entries_have_runtime_and_model(self, profile_name: str):
        for role, policy in get_profile(profile_name).items():
            for entry in policy["fallback_chain"]:
                assert set(entry.keys()) == {"runtime_kind", "model"}, role

    @pytest.mark.parametrize("profile_name", VALID_PROFILES)
    def test_gate_policy_is_valid(self, profile_name: str):
        for policy in get_profile(profile_name).values():
            assert policy["gate_policy"] in {"continue", "pause"}

    @pytest.mark.parametrize("profile_name", VALID_PROFILES)
    def test_runtime_model_pairs_are_valid(self, profile_name: str):
        for role, policy in get_profile(profile_name).items():
            assert is_valid_runtime_model_pair(policy["runtime_kind"], policy["model"]), role
            for fallback in policy["fallback_chain"]:
                assert is_valid_runtime_model_pair(
                    fallback["runtime_kind"], fallback["model"]
                ), role


class TestProfileBaselines:
    def test_test_profile_matches_baseline(self):
        assert get_profile("test") == EXPECTED_TEST_PROFILE

    def test_production_profile_matches_baseline(self):
        assert get_profile("production") == EXPECTED_PRODUCTION_PROFILE

    def test_no_test_role_uses_scarce_free_pool_as_primary(self):
        # openrouter/gpt-oss-120b:free (~50-1k RPD) must never be a 24/7 primary.
        for role, policy in get_profile("test").items():
            assert not (
                policy["runtime_kind"] == "openrouter-api"
                and policy["model"] == "openai/gpt-oss-120b:free"
            ), role

    def test_every_test_chain_ends_with_openrouter_last_resort(self):
        for role, policy in get_profile("test").items():
            last = policy["fallback_chain"][-1]
            assert last == {
                "runtime_kind": "openrouter-api",
                "model": "openai/gpt-oss-120b:free",
            }, role


class TestNewProfileConstraints:
    def test_test_2_contains_no_paid_runtimes(self):
        for policy in get_profile("test-2").values():
            assert policy["runtime_kind"] not in {
                "anthropic-api",
                "openai-api",
                "claude-cli",
                "codex-cli",
            }
            assert "kimi" not in policy["model"].lower()
            for fallback in policy["fallback_chain"]:
                assert fallback["runtime_kind"] not in {
                    "anthropic-api",
                    "openai-api",
                    "claude-cli",
                    "codex-cli",
                }
                assert "kimi" not in fallback["model"].lower()

    def test_test_2_pause_gates_match_spec(self):
        expected_pause_roles = {"sage", "trade_proposal", "execution", "post_trade_review"}
        actual_pause_roles = {
            role
            for role, policy in get_profile("test-2").items()
            if policy["gate_policy"] == "pause"
        }
        assert actual_pause_roles == expected_pause_roles

    def test_test_minimal_paid_only_uses_anthropic_for_three_critical_roles(self):
        paid_roles = {
            role
            for role, policy in get_profile("test-minimal-paid").items()
            if policy["runtime_kind"] == "anthropic-api"
        }
        assert paid_roles == {"sage", "trade_proposal", "post_trade_review"}

    def test_test_minimal_paid_pause_gates_match_spec(self):
        expected_pause_roles = {"sage", "trade_proposal", "execution", "post_trade_review"}
        actual_pause_roles = {
            role
            for role, policy in get_profile("test-minimal-paid").items()
            if policy["gate_policy"] == "pause"
        }
        assert actual_pause_roles == expected_pause_roles

    def test_test_minimal_paid_noncritical_roles_match_test_2(self):
        for role in EXPECTED_ROLES - {"sage", "trade_proposal", "post_trade_review"}:
            assert get_role_policy("test-minimal-paid", role) == get_role_policy("test-2", role)


class TestLocalFree24x7SafeProfile:
    def test_profile_matches_spec(self):
        assert get_profile("test-local-free-24x7-safe") == EXPECTED_LOCAL_FREE_24X7_PROFILE

    def test_primary_runtime_is_ollama_for_all_roles(self):
        for role, policy in get_profile("test-local-free-24x7-safe").items():
            assert policy["runtime_kind"] == "ollama", role

    def test_pause_gates_match_critical_roles(self):
        expected_pause_roles = {"sage", "trade_proposal", "execution", "post_trade_review"}
        actual_pause_roles = {
            role
            for role, policy in get_profile("test-local-free-24x7-safe").items()
            if policy["gate_policy"] == "pause"
        }
        assert actual_pause_roles == expected_pause_roles

    def test_critical_path_does_not_use_gpt_oss(self):
        critical_roles = {"sage", "trade_proposal", "execution", "post_trade_review"}
        for role in critical_roles:
            policy = get_role_policy("test-local-free-24x7-safe", role)
            assert policy is not None
            assert policy["model"] != "openai/gpt-oss-120b:free"
            for fallback in policy["fallback_chain"]:
                assert fallback["model"] != "openai/gpt-oss-120b:free"


class TestTestJamProfile:
    """test-jam = same free spread as `test` + pause gates on the 4 critical roles."""

    def test_pause_gates_match_critical_roles(self):
        expected_pause_roles = {"sage", "trade_proposal", "execution", "post_trade_review"}
        actual_pause_roles = {
            role
            for role, policy in get_profile("test-jam").items()
            if policy["gate_policy"] == "pause"
        }
        assert actual_pause_roles == expected_pause_roles

    def test_contains_no_paid_runtimes(self):
        for policy in get_profile("test-jam").values():
            assert policy["runtime_kind"] not in {
                "anthropic-api",
                "openai-api",
                "claude-cli",
                "codex-cli",
            }
            assert "kimi" not in policy["model"].lower()
            for fallback in policy["fallback_chain"]:
                assert fallback["runtime_kind"] not in {
                    "anthropic-api",
                    "openai-api",
                    "claude-cli",
                    "codex-cli",
                }
                assert "kimi" not in fallback["model"].lower()

    def test_no_role_uses_scarce_free_pool_as_primary(self):
        for role, policy in get_profile("test-jam").items():
            assert not (
                policy["runtime_kind"] == "openrouter-api"
                and policy["model"] == "openai/gpt-oss-120b:free"
            ), role

    def test_every_chain_ends_with_openrouter_last_resort(self):
        for role, policy in get_profile("test-jam").items():
            assert policy["fallback_chain"][-1] == {
                "runtime_kind": "openrouter-api",
                "model": "openai/gpt-oss-120b:free",
            }, role

    def test_noncritical_roles_match_test(self):
        # Only the 4 critical gates differ from `test`; everything else is identical.
        for role in EXPECTED_ROLES - {"sage", "trade_proposal", "execution", "post_trade_review"}:
            assert get_role_policy("test-jam", role) == get_role_policy("test", role)


class TestGetRolePolicy:
    def test_returns_policy_for_known_role(self):
        policy = get_role_policy("test", "execution")
        assert policy is not None
        assert policy["runtime_kind"] == "groq-api"

    def test_returns_none_for_unknown_role(self):
        assert get_role_policy("test", "nonexistent_role") is None


class TestClassifyAgentProfile:
    def test_matches_test_profile(self):
        result = classify_agent_profile(
            "test", "google-ai-studio", "gemini-2.0-flash", "news_monitor"
        )
        assert result == "test"

    def test_matches_test_2_profile(self):
        result = classify_agent_profile("test-2", "cerebras-api", "qwen-3-32b", "hawk_counter")
        assert result == "test-2"

    def test_matches_test_minimal_paid_profile(self):
        result = classify_agent_profile(
            "test-minimal-paid", "anthropic-api", "claude-opus-4-8", "sage"
        )
        assert result == "test-minimal-paid"

    def test_matches_test_local_free_24x7_safe_profile(self):
        result = classify_agent_profile(
            "test-local-free-24x7-safe", "ollama", "qwen3:14b", "sage"
        )
        assert result == "test-local-free-24x7-safe"

    def test_matches_production_profile(self):
        result = classify_agent_profile(
            "production", "groq-api", "llama-3.3-70b-versatile", "news_monitor"
        )
        assert result == "production"

    def test_custom_when_model_differs(self):
        assert (
            classify_agent_profile("test", "openrouter-api", "some-other-model", "news_monitor")
            == "custom"
        )

    def test_custom_for_unknown_role(self):
        assert (
            classify_agent_profile("test", "groq-api", "llama-3.3-70b-versatile", "unknown")
            == "custom"
        )


class TestMergeRuntimeToolsConfig:
    def test_writes_runtime_and_model(self):
        result = merge_runtime_tools_config(
            None, runtime_kind="groq-api", model="llama-3.3-70b-versatile"
        )
        assert result["runtime_kind"] == "groq-api"
        assert result["ai_backend"] == "groq-api"
        assert result["model"] == "llama-3.3-70b-versatile"

    def test_writes_fallback_chain_when_provided(self):
        chain = [
            {"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"}
        ]
        result = merge_runtime_tools_config(
            None, runtime_kind="groq-api", model="llama-3.3-70b-versatile", fallback_chain=chain
        )
        assert result["fallback_chain"] == chain

    def test_writes_gate_policy_when_provided(self):
        result = merge_runtime_tools_config(
            None, runtime_kind="groq-api", model="llama-3.3-70b-versatile", gate_policy="pause"
        )
        assert result["gate_policy"] == "pause"

    def test_does_not_write_fallback_chain_when_omitted(self):
        result = merge_runtime_tools_config(
            None, runtime_kind="groq-api", model="llama-3.3-70b-versatile"
        )
        assert "fallback_chain" not in result

    def test_does_not_write_gate_policy_when_omitted(self):
        result = merge_runtime_tools_config(
            None, runtime_kind="groq-api", model="llama-3.3-70b-versatile"
        )
        assert "gate_policy" not in result

    def test_preserves_existing_keys(self):
        result = merge_runtime_tools_config(
            {"source_key": "abc", "custom_field": "xyz"},
            runtime_kind="groq-api",
            model="llama-3.3-70b-versatile",
        )
        assert result["source_key"] == "abc"
        assert result["custom_field"] == "xyz"

    def test_overwrites_stale_runtime_in_existing_config(self):
        result = merge_runtime_tools_config(
            {"runtime_kind": "kimi-cli", "ai_backend": "kimi-cli", "model": "kimi-k2.6"},
            runtime_kind="groq-api",
            model="llama-3.3-70b-versatile",
        )
        assert result["runtime_kind"] == "groq-api"
        assert result["model"] == "llama-3.3-70b-versatile"
