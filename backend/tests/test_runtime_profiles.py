"""Tests for the two-mode runtime profile system."""

from __future__ import annotations

import pytest

from app.services.runtime_profiles import (
    RUNTIME_PROFILES,
    VALID_PROFILES,
    classify_agent_profile,
    get_profile,
    get_role_policy,
)
from app.services.agent_config import merge_runtime_tools_config


# ── Profile lookup ────────────────────────────────────────────────────────────


class TestGetProfile:
    def test_returns_test_profile(self):
        profile = get_profile("test")
        assert isinstance(profile, dict)
        assert "news_monitor" in profile

    def test_returns_production_profile(self):
        profile = get_profile("production")
        assert isinstance(profile, dict)
        assert "news_monitor" in profile

    def test_raises_for_unknown_profile(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            get_profile("staging")

    def test_all_valid_profiles_resolvable(self):
        for name in VALID_PROFILES:
            profile = get_profile(name)
            assert isinstance(profile, dict)


class TestProfileCompleteness:
    EXPECTED_ROLES = {
        "news_monitor", "source_reliability", "market_regime",
        "hawk_trend", "hawk_structure", "hawk_counter",
        "sage", "trade_proposal", "execution",
        "position_monitor", "trade_journal", "post_trade_review",
    }

    @pytest.mark.parametrize("profile_name", ["test", "production"])
    def test_all_12_roles_present(self, profile_name: str):
        profile = get_profile(profile_name)
        assert set(profile.keys()) == self.EXPECTED_ROLES

    @pytest.mark.parametrize("profile_name", ["test", "production"])
    def test_each_role_has_required_fields(self, profile_name: str):
        profile = get_profile(profile_name)
        for role, policy in profile.items():
            assert "runtime_kind" in policy, f"{profile_name}/{role} missing runtime_kind"
            assert "model" in policy, f"{profile_name}/{role} missing model"
            assert "fallback_chain" in policy, f"{profile_name}/{role} missing fallback_chain"
            assert "gate_policy" in policy, f"{profile_name}/{role} missing gate_policy"

    @pytest.mark.parametrize("profile_name", ["test", "production"])
    def test_fallback_chain_entries_have_runtime_and_model(self, profile_name: str):
        profile = get_profile(profile_name)
        for role, policy in profile.items():
            for i, entry in enumerate(policy["fallback_chain"]):
                assert "runtime_kind" in entry, f"{profile_name}/{role} fallback[{i}] missing runtime_kind"
                assert "model" in entry, f"{profile_name}/{role} fallback[{i}] missing model"

    @pytest.mark.parametrize("profile_name", ["test", "production"])
    def test_gate_policy_is_valid(self, profile_name: str):
        profile = get_profile(profile_name)
        valid_policies = {"continue", "pause"}
        for role, policy in profile.items():
            assert policy["gate_policy"] in valid_policies, (
                f"{profile_name}/{role} gate_policy '{policy['gate_policy']}' not in {valid_policies}"
            )


class TestGetRolePolicy:
    def test_returns_policy_for_known_role(self):
        policy = get_role_policy("test", "execution")
        assert policy is not None
        assert policy["runtime_kind"] == "groq-api"

    def test_returns_none_for_unknown_role(self):
        assert get_role_policy("test", "nonexistent_role") is None


class TestClassifyAgentProfile:
    def test_matches_test_profile(self):
        result = classify_agent_profile("test", "groq-api", "llama-3.3-70b-versatile", "news_monitor")
        assert result == "test"

    def test_matches_production_profile(self):
        result = classify_agent_profile("production", "kimi-cli", "kimi-k2.6", "news_monitor")
        assert result == "production"

    def test_custom_when_model_differs(self):
        result = classify_agent_profile("test", "groq-api", "some-other-model", "news_monitor")
        assert result == "custom"

    def test_custom_for_unknown_role(self):
        result = classify_agent_profile("test", "groq-api", "llama-3.3-70b-versatile", "unknown_role")
        assert result == "custom"


# ── merge_runtime_tools_config ────────────────────────────────────────────────


class TestMergeRuntimeToolsConfig:
    def test_writes_runtime_and_model(self):
        result = merge_runtime_tools_config(None, runtime_kind="groq-api", model="llama-3.3-70b-versatile")
        assert result["runtime_kind"] == "groq-api"
        assert result["ai_backend"] == "groq-api"
        assert result["model"] == "llama-3.3-70b-versatile"

    def test_writes_fallback_chain_when_provided(self):
        chain = [{"runtime_kind": "openrouter-api", "model": "meta-llama/llama-3.3-70b-instruct:free"}]
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
        result = merge_runtime_tools_config(None, runtime_kind="groq-api", model="llama-3.3-70b-versatile")
        assert "fallback_chain" not in result

    def test_does_not_write_gate_policy_when_omitted(self):
        result = merge_runtime_tools_config(None, runtime_kind="groq-api", model="llama-3.3-70b-versatile")
        assert "gate_policy" not in result

    def test_preserves_existing_keys(self):
        existing = {"source_key": "abc", "custom_field": "xyz"}
        result = merge_runtime_tools_config(
            existing, runtime_kind="groq-api", model="llama-3.3-70b-versatile"
        )
        assert result["source_key"] == "abc"
        assert result["custom_field"] == "xyz"

    def test_overwrites_stale_runtime_in_existing_config(self):
        existing = {"runtime_kind": "kimi-cli", "ai_backend": "kimi-cli", "model": "kimi-k2.6"}
        result = merge_runtime_tools_config(
            existing, runtime_kind="groq-api", model="llama-3.3-70b-versatile"
        )
        assert result["runtime_kind"] == "groq-api"
        assert result["model"] == "llama-3.3-70b-versatile"


# ── Profile ↔ agent mapping correctness ──────────────────────────────────────


class TestTestProfileMappings:
    """Spot-check specific test profile assignments per the spec."""

    def test_execution_uses_groq_small(self):
        p = get_role_policy("test", "execution")
        assert p["runtime_kind"] == "groq-api"
        assert p["model"] == "llama-3.1-8b-instant"

    def test_sage_uses_openrouter_free(self):
        p = get_role_policy("test", "sage")
        assert p["runtime_kind"] == "openrouter-api"
        assert "free" in p["model"]

    def test_source_reliability_uses_openrouter(self):
        p = get_role_policy("test", "source_reliability")
        assert p["runtime_kind"] == "openrouter-api"


class TestProductionProfileMappings:
    """Spot-check production profile assignments per the spec."""

    def test_execution_unchanged_in_production(self):
        p = get_role_policy("production", "execution")
        assert p["runtime_kind"] == "groq-api"
        assert p["model"] == "llama-3.1-8b-instant"

    def test_sage_uses_claude_opus(self):
        p = get_role_policy("production", "sage")
        assert p["runtime_kind"] == "claude-cli"
        assert "opus" in p["model"]

    def test_critical_roles_have_pause_gate(self):
        critical = ["sage", "trade_proposal", "execution", "source_reliability", "post_trade_review"]
        for role in critical:
            p = get_role_policy("production", role)
            assert p["gate_policy"] == "pause", f"Expected pause gate for {role} in production"

    def test_news_monitor_uses_kimi(self):
        p = get_role_policy("production", "news_monitor")
        assert p["runtime_kind"] == "kimi-cli"
        assert p["model"] == "kimi-k2.6"
