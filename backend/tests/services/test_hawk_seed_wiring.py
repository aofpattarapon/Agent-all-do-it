"""Tests for the HAWK market_data handoff wiring.

Two things are guarded here:

1. SEED WIRING — every HAWK step in the crypto trade-pipeline workflows must inject the
   live market data via the $market_data_hawk token. The seed applies step prompts from
   per-workflow prompt maps (_TRADE_PIPELINE_STEP_PROMPTS / _AUTO_PIPELINE_STEP_PROMPTS)
   inside _materialize_workflow_definition() — NOT from inline step config — so these tests
   assert against the materialized definition and the prompt maps, which is what actually
   reaches the database on seed.

2. LEAN $market_data — recent_candles are a HAWK-only enrichment exposed through
   $market_data_hawk. The general-purpose $market_data token must stay lean (no
   recent_candles) so non-HAWK agents are not bloated, while context["market_data"]
   itself is left untouched.

Complements tests/services/test_hawk_injection.py (substitution / gate / dq_flags) and
tests/services/test_market_data_renderer.py (renderer output shape).
"""

from __future__ import annotations

import json

from app.commands.seed_crypto_workflow import (
    CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_WORKFLOW,
    _materialize_workflow_definition,
    _workflow_prompt_map,
)
from app.services.indicators import compute_all
from app.services.run_executor import RunExecutor

_HAWK_STEP_KEYS = {"hawk_trend", "hawk_structure", "hawk_counter"}
_PIPELINE_WORKFLOWS = (
    CRYPTO_TRADE_PIPELINE_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW,
)


def _make_klines(n: int = 20) -> list[list]:
    rows = []
    for i in range(n):
        o = 100.0 + i
        rows.append([i * 3600000, o, o + 2, o - 1, o + 1, 10.0 + i * 0.5, 0, 0, 0, 0, 0, 0])
    return rows


def _hawk_context(with_candles: bool = True) -> dict:
    indicators = compute_all(_make_klines(20), include_recent_candles=with_candles)
    return {
        "input_payload": {"symbol": "BTCUSDT"},
        "market_data": {
            "symbol": "BTCUSDT",
            "price": 107000.0,
            "funding_rate": 0.0001,
            "long_short_ratio": 1.2,
            "fear_greed": {"value": 72, "value_classification": "Greed"},
            "indicators": {"4h": indicators, "1h": indicators, "1d": indicators},
            "errors": [],
        },
        "last_output": "",
        "monitor_snapshot": None,
    }


# ---------------------------------------------------------------------------
# Seed wiring — materialized HAWK steps must inject $market_data_hawk
# ---------------------------------------------------------------------------


def _materialized_hawk_steps(workflow: dict) -> list[dict]:
    # agent id map is irrelevant to prompt injection; pass empty.
    definition = _materialize_workflow_definition(workflow, {})
    return [s for s in definition["steps"] if s.get("key") in _HAWK_STEP_KEYS]


def test_all_pipeline_workflows_materialize_market_data_hawk() -> None:
    for workflow in _PIPELINE_WORKFLOWS:
        steps = _materialized_hawk_steps(workflow)
        assert {s["key"] for s in steps} == _HAWK_STEP_KEYS, workflow["name"]
        for step in steps:
            prompt = step["config"]["prompt"]
            assert "$market_data_hawk" in prompt, f"{workflow['name']}/{step['key']}"


def test_materialized_hawk_prompt_does_not_use_legacy_market_data_token() -> None:
    """HAWK steps should rely on the compact $market_data_hawk view, not the legacy token.

    ($market_data_hawk contains the substring "$market_data", so we check the legacy token
    is not present as a *standalone* reference by stripping the hawk token first.)
    """
    for workflow in _PIPELINE_WORKFLOWS:
        for step in _materialized_hawk_steps(workflow):
            stripped = step["config"]["prompt"].replace("$market_data_hawk", "")
            assert "$market_data" not in stripped, f"{workflow['name']}/{step['key']}"


def test_prompt_maps_cover_every_hawk_step_with_handoff_fields() -> None:
    """The per-workflow prompt maps must carry $market_data_hawk and reference the
    handoff fields (recent_candles) HAWK needs for invalidation_level."""
    for workflow in _PIPELINE_WORKFLOWS:
        prompt_map = _workflow_prompt_map(workflow["name"])
        for key in _HAWK_STEP_KEYS:
            prompt = prompt_map.get(key, "")
            assert "$market_data_hawk" in prompt, f"{workflow['name']}/{key} token"
            assert "recent_candles" in prompt, f"{workflow['name']}/{key} candles"


def test_auto_hawk_prompts_include_required_handoff_schema() -> None:
    required_terms = (
        '"agent"',
        '"symbol"',
        '"analyzed_at"',
        '"sources_used"',
        '"vote"',
        '"confidence"',
        '"data_quality"',
        '"market_data_snapshot"',
        '"invalidation_level"',
        '"risk_flags"',
        '"reasoning"',
    )
    auto_workflows = (CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW, CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW)

    for workflow in auto_workflows:
        prompt_map = _workflow_prompt_map(workflow["name"])
        for key in _HAWK_STEP_KEYS:
            prompt = prompt_map.get(key, "")
            for term in required_terms:
                assert term in prompt, f"{workflow['name']}/{key} missing {term}"
            assert "Minimal valid JSON example" in prompt
            assert "BULLISH" in prompt
            assert "BEARISH" in prompt
            assert "NEUTRAL" in prompt


def test_auto_hawk_prompts_include_role_specific_examples() -> None:
    role_terms = {
        "hawk_trend": (
            "Role-specific valid JSON example for hawk_trend",
            '"role_focus": "trend"',
            "HAWK-TREND SPECIFIC RULE",
            '"reasoning.trend_assessment"',
            '"trend_assessment"',
        ),
        "hawk_structure": (
            "Role-specific valid JSON example for hawk_structure",
            '"role_focus": "structure"',
            "HAWK-STRUCTURE SPECIFIC RULE",
        ),
        "hawk_counter": (
            "Role-specific valid JSON example for hawk_counter",
            '"role_focus": "counter"',
            "HAWK-COUNTER SPECIFIC RULE",
            '"reasoning.counter_assessment"',
            '"counter_assessment"',
            'use [] when no counter-trend risks are detected',
        ),
    }
    auto_workflows = (CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW, CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW)

    for workflow in auto_workflows:
        prompt_map = _workflow_prompt_map(workflow["name"])
        for key, terms in role_terms.items():
            prompt = prompt_map.get(key, "")
            for term in terms:
                assert term in prompt, f"{workflow['name']}/{key} missing {term}"


def test_auto_hawk_structure_prompt_forbids_partial_risk_only_json() -> None:
    auto_workflows = (CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW, CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW)

    for workflow in auto_workflows:
        prompt = _workflow_prompt_map(workflow["name"]).get("hawk_structure", "")
        assert 'Returning only {"risk_flags": [], "invalidation_level": <number>} is INVALID' in prompt
        assert "Structure analysis must still include vote, confidence" in prompt


def test_auto_hawk_prompts_reject_analysis_shaped_top_level_json() -> None:
    auto_workflows = (CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW, CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW)

    for workflow in auto_workflows:
        prompt_map = _workflow_prompt_map(workflow["name"])
        for key in _HAWK_STEP_KEYS:
            prompt = prompt_map.get(key, "")
            assert "Do NOT use alternative top-level keys" in prompt
            assert '"trend_direction"' in prompt
            assert '"analysis"' in prompt
            assert '"conclusion"' in prompt
            assert '"recommendation"' in prompt
            assert 'inside "reasoning" only' in prompt


# ---------------------------------------------------------------------------
# $market_data stays lean; $market_data_hawk keeps recent_candles
# ---------------------------------------------------------------------------


def test_market_data_token_excludes_recent_candles() -> None:
    ctx = _hawk_context(with_candles=True)
    rendered = RunExecutor._substitute("$market_data", ctx)
    assert "recent_candles" not in rendered
    # but indicators are still present
    assert "ema_20" in rendered
    assert "vwap" in rendered


def test_market_data_hawk_token_includes_recent_candles() -> None:
    ctx = _hawk_context(with_candles=True)
    rendered = RunExecutor._substitute("$market_data_hawk", ctx)
    assert "recent_candles" in rendered


def test_substitute_does_not_mutate_context_market_data() -> None:
    """Stripping recent_candles for $market_data must use a copy — context stays intact."""
    ctx = _hawk_context(with_candles=True)
    RunExecutor._substitute("$market_data $market_data_hawk", ctx)
    assert "recent_candles" in ctx["market_data"]["indicators"]["4h"]


def test_market_data_token_still_valid_json() -> None:
    ctx = _hawk_context(with_candles=True)
    rendered = RunExecutor._substitute("$market_data", ctx)
    parsed = json.loads(rendered)
    assert parsed["symbol"] == "BTCUSDT"
    assert "4h" in parsed["indicators"]
