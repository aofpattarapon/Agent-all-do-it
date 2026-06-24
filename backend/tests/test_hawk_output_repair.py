"""Tests for HAWK output repair / normalization."""

from __future__ import annotations

import json

import pytest

from app.services.hawk_output_repair import (
    build_hawk_repair_prompt,
    format_hawk_block_details,
    repair_hawk_output,
)


def test_valid_hawk_json_passes_unchanged() -> None:
    raw = json.dumps(
        {
            "agent": "hawk_trend",
            "vote": "BULLISH",
            "confidence": 72,
            "invalidation_level": 65000.0,
            "sources_used": ["pre-fetched market data"],
            "risk_flags": [],
            "reasoning": "EMA stack is bullish.",
        }
    )
    payload, meta = repair_hawk_output(raw, role="hawk_trend")
    assert payload is not None
    assert payload["vote"] == "BULLISH"
    assert payload["confidence"] == 72
    assert meta["repaired"] is False
    assert meta["repair_notes"] == []


def test_markdown_wrapped_json_is_repaired() -> None:
    raw = "```json\n{\"vote\": \"BULLISH\", \"confidence\": 65}\n```"
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert payload["vote"] == "BULLISH"
    assert payload["confidence"] == 65
    assert meta["repaired"] is True


def test_prose_plus_json_is_repaired() -> None:
    raw = "Here is my analysis:\n```json\n{\"vote\": \"BEARISH\", \"confidence\": 80}\n```\nHope this helps."
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert payload["vote"] == "BEARISH"
    assert payload["confidence"] == 80
    assert meta["repaired"] is True


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("LONG", "BULLISH"),
        ("BUY", "BULLISH"),
        ("SHORT", "BEARISH"),
        ("SELL", "BEARISH"),
        ("HOLD", "NEUTRAL"),
        ("SKIP", "NEUTRAL"),
        ("REJECT", "VETO"),
    ],
)
def test_vote_aliases_normalized(alias: str, expected: str) -> None:
    raw = json.dumps({"vote": alias, "confidence": 50})
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert payload["vote"] == expected
    assert meta["repaired"] is True
    assert any("normalized" in note for note in meta["repair_notes"])


def test_confidence_decimal_scaled_to_100() -> None:
    raw = json.dumps({"vote": "BULLISH", "confidence": 0.72})
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert payload["confidence"] == 72


def test_confidence_string_parsed() -> None:
    raw = json.dumps({"vote": "BULLISH", "confidence": "65"})
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert payload["confidence"] == 65


def test_missing_confidence_with_neutral_set_to_zero() -> None:
    raw = json.dumps({"vote": "NEUTRAL"})
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert payload["confidence"] == 0
    assert meta["repaired"] is True


def test_missing_confidence_with_bullish_left_missing() -> None:
    raw = json.dumps({"vote": "BULLISH"})
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert "confidence" not in payload or payload["confidence"] is None
    # Confidence must NOT be silently invented for a directional vote.
    assert not any("confidence" in note and "set to" in note for note in meta["repair_notes"])


def test_risk_flags_defaulted_to_empty_array() -> None:
    raw = json.dumps({"vote": "NEUTRAL", "confidence": 40})
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert payload["risk_flags"] == []
    assert meta["repaired"] is True


def test_sources_used_wrapped_when_string() -> None:
    raw = json.dumps({"vote": "BULLISH", "confidence": 70, "sources_used": "market_data"})
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert payload["sources_used"] == ["market_data"]
    assert meta["repaired"] is True


def test_sources_used_not_invented_when_missing() -> None:
    raw = json.dumps({"vote": "BULLISH", "confidence": 70})
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert "sources_used" not in payload
    assert not any("sources_used" in note for note in meta["repair_notes"])


def test_repair_metadata_includes_raw_preview() -> None:
    raw = json.dumps({"vote": "LONG", "confidence": "55"})
    payload, meta = repair_hawk_output(raw)
    assert payload is not None
    assert "raw_preview" in meta
    assert meta["repaired"] is True
    assert "LONG" in meta["raw_preview"]


def test_empty_output_returns_none() -> None:
    payload, meta = repair_hawk_output("")
    assert payload is None
    assert meta["original_parse_error"] == "empty output"


def test_invalid_json_returns_none() -> None:
    payload, meta = repair_hawk_output("this is not json")
    assert payload is None
    assert "no JSON object found" in (meta["original_parse_error"] or "")


def test_build_hawk_repair_prompt_contains_schema_and_original() -> None:
    original = json.dumps({"vote": "BULLISH"})
    prompt = build_hawk_repair_prompt(original, role="hawk_trend")
    assert "Convert the previous answer into valid JSON only" in prompt
    assert "Previous output:" in prompt
    assert "BULLISH" in prompt
    assert "vote" in prompt
    assert '"agent": "hawk_trend"' in prompt
    assert '"sources_used": ["pre-fetched market data"]' in prompt
    assert '"data_quality": "REAL_MARKET_DATA" | "PARTIAL"' in prompt
    assert '"market_data_snapshot"' in prompt
    assert '"risk_flags": []' in prompt
    assert '"reasoning": {"role_focus": "<hawk role>"' in prompt


def test_build_hawk_repair_prompt_rejects_analysis_top_level_keys() -> None:
    # Include a valid vote so this hits preserve mode (which retains the forbidden-key warning).
    original = json.dumps({"vote": "BULLISH", "analysis": "support held", "invalidation_level": 64000})
    prompt = build_hawk_repair_prompt(original, role="hawk_structure")

    assert "Do not use top-level trend_direction, analysis, conclusion, or recommendation" in prompt
    assert 'If risk_flags is missing, include "risk_flags": []' in prompt
    assert 'move it under "reasoning"' in prompt


def test_format_hawk_block_details_structured_json() -> None:
    class FakeViolation:
        def __init__(self, field: str, reason: str, critical: bool = True) -> None:
            self.field = field
            self.reason = reason
            self.critical = critical

    violations = [
        FakeViolation("vote", "must be one of ..."),
        FakeViolation("confidence", "missing or null", critical=False),
    ]
    details = format_hawk_block_details(
        step_key="hawk_trend",
        role="hawk_trend",
        model="qwen3:14b",
        violations=violations,
        raw_preview='{"vote": null}',
        repaired=True,
        retry_attempted=True,
    )
    parsed = json.loads(details)
    assert parsed["step"] == "hawk_trend"
    assert parsed["model"] == "qwen3:14b"
    assert parsed["missing_fields"] == ["confidence"]
    assert parsed["repaired"] is True
    assert parsed["retry_attempted"] is True
