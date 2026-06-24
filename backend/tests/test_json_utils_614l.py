"""Phase 6.14.L — Tests for json_utils normalize_llm_json_output and extract_json_object."""

from __future__ import annotations

import json

import pytest

from app.core.json_utils import extract_json_object, normalize_llm_json_output


# ── Fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_PROPOSAL = {
    "agent": "crypto_trade_proposal",
    "direction": "SHORT",
    "approval_status": "PENDING_APPROVAL",
    "entry_plan": {"primary_entry": 64000.0},
    "stop_loss": 65500.0,
    "take_profit": [{"tp_level": 62000.0}, {"tp_level": 60000.0}],
    "risk_reward": 2.5,
    "position_size_usdt": 50.0,
    "market_type": "futures",
}

RAW_JSON = json.dumps(MINIMAL_PROPOSAL)
FENCED_JSON = f"```json\n{RAW_JSON}\n```"
FENCED_NO_LANG = f"```\n{RAW_JSON}\n```"
FENCED_EXTRA_WHITESPACE = f"```json\n\n  {RAW_JSON}\n\n```"

# Truncated at mid-JSON (simulates gemini hitting token ceiling)
TRUNCATED_JSON = '```json\n{\n  "agent": "crypto_trade_proposal",\n  "direction": "SHORT",\n  "entry_plan": {\n    "primary_entry": 64000'
TRUNCATED_NO_FENCE = '{\n  "agent": "crypto_trade_proposal",\n  "direction": "SHORT",\n  "entry_plan": {\n    "primary_entry": 64000'

PROSE_PLUS_JSON = f"Here is the proposal:\n{RAW_JSON}\nEnd of proposal."
PROSE_PLUS_TRUNCATED = f"Here is the proposal:\n" + '{"agent": "x", "entry": 123'


# ── normalize_llm_json_output ─────────────────────────────────────────────────


def test_raw_json_passes() -> None:
    parsed, meta = normalize_llm_json_output(RAW_JSON)
    assert parsed is not None
    assert parsed["direction"] == "SHORT"
    assert meta["had_markdown_fence"] is False
    assert meta["repaired_json_wrapper"] is False
    assert meta["truncated_detected"] is False
    assert meta["parse_error"] is None


def test_fenced_json_passes_after_extraction() -> None:
    parsed, meta = normalize_llm_json_output(FENCED_JSON)
    assert parsed is not None
    assert parsed["direction"] == "SHORT"
    assert meta["had_markdown_fence"] is True
    assert meta["repaired_json_wrapper"] is True
    assert meta["truncated_detected"] is False
    assert meta["parse_error"] is None


def test_fenced_no_lang_tag_passes() -> None:
    parsed, meta = normalize_llm_json_output(FENCED_NO_LANG)
    assert parsed is not None
    assert meta["had_markdown_fence"] is True
    assert meta["repaired_json_wrapper"] is True


def test_fenced_json_with_extra_whitespace_passes() -> None:
    parsed, meta = normalize_llm_json_output(FENCED_EXTRA_WHITESPACE)
    assert parsed is not None
    assert meta["had_markdown_fence"] is True
    assert meta["repaired_json_wrapper"] is True


def test_truncated_fenced_json_returns_parse_error_and_blocks() -> None:
    parsed, meta = normalize_llm_json_output(TRUNCATED_JSON)
    assert parsed is None
    assert meta["truncated_detected"] is True
    assert meta["had_markdown_fence"] is True
    assert meta["parse_error"] == "compile_proposal_invalid_json_truncated"


def test_truncated_json_no_fence_returns_parse_error() -> None:
    parsed, meta = normalize_llm_json_output(TRUNCATED_NO_FENCE)
    assert parsed is None
    assert meta["truncated_detected"] is True
    assert meta["parse_error"] == "compile_proposal_invalid_json_truncated"


def test_prose_plus_one_complete_json_extracts_correctly() -> None:
    parsed, meta = normalize_llm_json_output(PROSE_PLUS_JSON)
    assert parsed is not None
    assert parsed["direction"] == "SHORT"
    assert meta["repaired_json_wrapper"] is True


def test_prose_plus_truncated_json_blocks() -> None:
    parsed, meta = normalize_llm_json_output(PROSE_PLUS_TRUNCATED)
    assert parsed is None
    assert meta["truncated_detected"] is True


def test_empty_string_returns_empty_output_error() -> None:
    parsed, meta = normalize_llm_json_output("")
    assert parsed is None
    assert meta["parse_error"] == "empty_output"


def test_non_json_text_returns_no_json_object_found() -> None:
    parsed, meta = normalize_llm_json_output("The market looks bearish today.")
    assert parsed is None
    assert meta["parse_error"] == "no_json_object_found"


def test_missing_required_field_still_parsed_but_no_fabrication() -> None:
    # normalize_llm_json_output only parses — field validation is the caller's job.
    payload_no_direction = {k: v for k, v in MINIMAL_PROPOSAL.items() if k != "direction"}
    parsed, meta = normalize_llm_json_output(json.dumps(payload_no_direction))
    assert parsed is not None
    assert "direction" not in parsed
    assert meta["parse_error"] is None


def test_multiple_json_objects_extracts_first_only() -> None:
    # Balanced-brace extractor returns first complete object, not the second.
    text = f'{RAW_JSON}\n{{"second": true}}'
    parsed, meta = normalize_llm_json_output(text)
    assert parsed is not None
    assert parsed.get("direction") == "SHORT"
    assert "second" not in parsed


# ── extract_json_object (regression) ─────────────────────────────────────────


def test_extract_raw_json_still_works() -> None:
    assert extract_json_object(RAW_JSON) == MINIMAL_PROPOSAL


def test_extract_fenced_json_still_works() -> None:
    result = extract_json_object(FENCED_JSON)
    assert result is not None
    assert result["direction"] == "SHORT"


def test_extract_truncated_returns_none() -> None:
    # Truncated input must not return a partial object.
    assert extract_json_object(TRUNCATED_NO_FENCE) is None


def test_extract_empty_returns_none() -> None:
    assert extract_json_object("") is None


def test_extract_prose_wrapped_returns_first_object() -> None:
    result = extract_json_object(PROSE_PLUS_JSON)
    assert result is not None
    assert result["direction"] == "SHORT"


# ── Phase 6.14.L specific: the exact gemini failure scenario ─────────────────


def test_gemini_truncated_output_blocks_correctly() -> None:
    """Reproduce the exact failure from Phase 6.14.K run eb439a1a."""
    gemini_output = (
        "```json\n"
        "{\n"
        '  "agent": "crypto_trade_proposal",\n'
        '  "compiled_at": "2026-06-18T14:18:58.622670+00:00",\n'
        '  "symbol": "BTCUSDT",\n'
        '  "direction": "SHORT",\n'
        '  "strategy_type": "TREND_CONTINUATION",\n'
        '  "time_horizon": "SWING",\n'
        '  "market_context": {\n'
        '    "regime": "BEARISH_TREND",\n'
        '    "fear_greed": 15,\n'
        '    "key_news": []\n'
        "  },\n"
        '  "entry_plan": {\n'
        '    "primary_entry": 64491'
    )
    parsed, meta = normalize_llm_json_output(gemini_output)
    assert parsed is None
    assert meta["had_markdown_fence"] is True
    assert meta["truncated_detected"] is True
    assert meta["parse_error"] == "compile_proposal_invalid_json_truncated"


def test_gemini_fenced_but_complete_output_passes() -> None:
    """A complete fenced gemini response must be repaired and pass."""
    complete_proposal = dict(MINIMAL_PROPOSAL)
    gemini_output = f"```json\n{json.dumps(complete_proposal)}\n```"
    parsed, meta = normalize_llm_json_output(gemini_output)
    assert parsed is not None
    assert parsed["direction"] == "SHORT"
    assert meta["had_markdown_fence"] is True
    assert meta["repaired_json_wrapper"] is True
    assert meta["truncated_detected"] is False
    assert meta["parse_error"] is None
