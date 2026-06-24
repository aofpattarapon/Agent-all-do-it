"""Deterministic repair / normalization for HAWK agent JSON outputs.

Called by RunExecutor before the crypto handoff validator runs.  The goal is to
recover from common local-model formatting mistakes (markdown fences, prose
wrappers, vote aliases, numeric strings, missing confidence on NEUTRAL) while
remaining strictly fail-closed for genuinely unsafe or ambiguous directional
votes.

Rules:
- Never invent market evidence.
- Never change a vote decision unless the alias mapping is unambiguous.
- Never silently pass a BULLISH/BEARISH/VETO output that is missing confidence.
- Record every repair in metadata so debugging is transparent.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.json_utils import extract_json_object

logger = logging.getLogger(__name__)


# Canonical HAWK vote values.  HAWK agents do not have veto authority; VETO is
# accepted in the repair layer only so that an explicit REJECT alias is mapped
# to a value that downstream safety will block, not approve.
_CANONICAL_VOTES = {"BULLISH", "BEARISH", "NEUTRAL", "VETO"}

_VOTE_ALIASES: dict[str, str] = {
    "LONG": "BULLISH",
    "BUY": "BULLISH",
    "UP": "BULLISH",
    "SHORT": "BEARISH",
    "SELL": "BEARISH",
    "DOWN": "BEARISH",
    "HOLD": "NEUTRAL",
    "SKIP": "NEUTRAL",
    "WAIT": "NEUTRAL",
    "FLAT": "NEUTRAL",
    "REJECT": "VETO",
    "BLOCK": "VETO",
    "DENY": "VETO",
}

# Phase 6.7 — Role-specific forbidden top-level keys.  The general forbidden set
# (trend_direction, analysis, conclusion, recommendation) is listed inline in the
# repair prompt; these role-specific extras extend that list per HAWK role.
_ROLE_EXTRA_FORBIDDEN: dict[str, list[str]] = {
    "hawk_trend": ["ema_alignment", "price_structure", "macd_signal"],
    "hawk_structure": [
        "price_vs_vwap",
        "structure_assessment",
        "active_order_block",
        "nearest_support_levels",
        "nearest_resistance_levels",
    ],
    "hawk_counter": ["rsi_signal", "funding_signal", "crowd_positioning", "counter_signals_found"],
}

# Where each role must nest its role-specific fields instead of top-level.
_ROLE_NESTING_HINT: dict[str, str] = {
    "hawk_trend": (
        'Place trend_direction, ema_alignment, price_structure, and macd_signal inside '
        '"reasoning.trend_assessment", not at the top level. '
        'Example: "reasoning": {"trend_assessment": {"direction": "UPTREND", "ema_alignment": "20>50>200"}}.'
    ),
    "hawk_structure": (
        'Place price_vs_vwap, active_order_block, nearest_support_levels, and '
        'nearest_resistance_levels inside "reasoning.structure_assessment", not at the top level.'
    ),
    "hawk_counter": (
        'Place rsi_signal, funding_signal, and crowd_positioning inside '
        '"reasoning.counter_assessment", not at the top level.'
    ),
}

# Compact valid JSON examples — one per HAWK role showing the correct nested shape.
# These are included in the repair prompt so the model has a concrete reference.
_HAWK_REPAIR_EXAMPLES: dict[str, str] = {
    "hawk_trend": (
        "{\n"
        '  "agent": "hawk_trend",\n'
        '  "symbol": "BTCUSDT",\n'
        '  "analyzed_at": "2025-01-01T00:00:00Z",\n'
        '  "sources_used": ["pre-fetched market data"],\n'
        '  "vote": "BULLISH",\n'
        '  "confidence": 68,\n'
        '  "data_quality": "REAL_MARKET_DATA",\n'
        '  "market_data_snapshot": {"price": 95000.0, "analyzed_interval": "4h"},\n'
        '  "invalidation_level": 91000.0,\n'
        '  "risk_flags": [],\n'
        '  "reasoning": {\n'
        '    "role_focus": "trend",\n'
        '    "summary": "EMA stack bullish, price making higher highs.",\n'
        '    "trend_assessment": {\n'
        '      "direction": "UPTREND",\n'
        '      "ema_alignment": "20 > 50 > 200",\n'
        '      "price_structure": "HH_HL",\n'
        '      "macd_signal": "BULLISH"\n'
        "    }\n"
        "  }\n"
        "}"
    ),
    "hawk_structure": (
        "{\n"
        '  "agent": "hawk_structure",\n'
        '  "symbol": "BTCUSDT",\n'
        '  "analyzed_at": "2025-01-01T00:00:00Z",\n'
        '  "sources_used": ["pre-fetched market data"],\n'
        '  "vote": "BULLISH",\n'
        '  "confidence": 65,\n'
        '  "data_quality": "REAL_MARKET_DATA",\n'
        '  "market_data_snapshot": {"price": 95000.0, "analyzed_interval": "1h"},\n'
        '  "invalidation_level": 90500.0,\n'
        '  "risk_flags": [],\n'
        '  "reasoning": {\n'
        '    "role_focus": "structure",\n'
        '    "summary": "Price above VWAP with demand order block support.",\n'
        '    "structure_assessment": {\n'
        '      "price_vs_vwap": "ABOVE",\n'
        '      "active_order_block": 91000.0,\n'
        '      "nearest_support_levels": [91000.0, 89500.0],\n'
        '      "nearest_resistance_levels": [97000.0, 100000.0]\n'
        "    }\n"
        "  }\n"
        "}"
    ),
    "hawk_counter": (
        "{\n"
        '  "agent": "hawk_counter",\n'
        '  "symbol": "BTCUSDT",\n'
        '  "analyzed_at": "2025-01-01T00:00:00Z",\n'
        '  "sources_used": ["pre-fetched market data"],\n'
        '  "vote": "NEUTRAL",\n'
        '  "confidence": 0,\n'
        '  "data_quality": "REAL_MARKET_DATA",\n'
        '  "market_data_snapshot": {"price": 95000.0, "analyzed_interval": "1h"},\n'
        '  "invalidation_level": null,\n'
        '  "risk_flags": [],\n'
        '  "reasoning": {\n'
        '    "role_focus": "counter",\n'
        '    "summary": "No significant counter-trend signals detected.",\n'
        '    "counter_assessment": {\n'
        '      "rsi_signal": "NEUTRAL",\n'
        '      "funding_signal": "NEUTRAL",\n'
        '      "crowd_positioning": "BALANCED"\n'
        "    }\n"
        "  }\n"
        "}"
    ),
}


def _safe_truncate(text: str | None, max_len: int = 800) -> str:
    """Return a safely truncated, single-line preview of raw text."""
    if text is None:
        return ""
    cleaned = " ".join(text.splitlines())
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3] + "..."
    return cleaned


def assess_hawk_output_reliability(
    raw_text: str | None,
    *,
    tokens_used: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Classify a HAWK raw output for observability — pure, no side effects.

    Returns booleans / short strings only.  Never raises, never logs, and never
    includes the raw payload, so it is safe to merge straight into step meta.

    Keys:
    - ``invalid_json``: output is empty or contains no parseable JSON object.
    - ``output_truncated_detected``: output appears cut off (hit the token
      ceiling, or invalid JSON with an unterminated/unbalanced object such as a
      bare ``"{"``).
    - ``reached_token_ceiling``: ``tokens_used >= max_tokens`` (both known).
    - ``parse_error``: short, safe reason string when ``invalid_json`` (no raw
      content); ``None`` otherwise.
    """
    text = raw_text or ""
    stripped = text.strip()
    payload = extract_json_object(text) if stripped else None
    invalid_json = stripped == "" or not isinstance(payload, dict)

    reached_ceiling = bool(
        isinstance(tokens_used, int)
        and isinstance(max_tokens, int)
        and max_tokens > 0
        and tokens_used >= max_tokens
    )

    # Heuristic truncation: invalid JSON whose braces are unbalanced or which
    # does not close on an object/array boundary (e.g. a lone "{").
    unbalanced = stripped.count("{") > stripped.count("}")
    looks_truncated = invalid_json and (
        stripped == "{" or unbalanced or (stripped != "" and not stripped.endswith(("}", "]")))
    )
    truncated = bool(reached_ceiling or (invalid_json and looks_truncated))

    parse_error: str | None = None
    if invalid_json:
        if stripped == "":
            parse_error = "empty output"
        elif payload is None:
            parse_error = "no JSON object found"
        else:
            parse_error = f"parsed JSON is {type(payload).__name__}, not object"

    return {
        "invalid_json": invalid_json,
        "output_truncated_detected": truncated,
        "reached_token_ceiling": reached_ceiling,
        "parse_error": parse_error,
    }


def _normalize_vote(value: Any, repair_notes: list[str]) -> Any:
    """Map unambiguous vote aliases to canonical values."""
    if not isinstance(value, str):
        return value
    upper = value.strip().upper()
    if upper in _CANONICAL_VOTES:
        return upper
    canonical = _VOTE_ALIASES.get(upper)
    if canonical is not None:
        repair_notes.append(f"vote alias '{value}' normalized to '{canonical}'")
        return canonical
    return value


def _normalize_confidence(value: Any, vote: Any, repair_notes: list[str]) -> Any:
    """Normalize confidence to a numeric 0-100 scale.

    - 0-1 floats are scaled to 0-100.
    - Numeric strings are parsed.
    - Missing/null confidence with NEUTRAL vote is set to 0.
    - Missing/null confidence with BULLISH/BEARISH/VETO is left missing so the
      caller can decide to retry or block.
    """
    if value is None or value == "":
        vote_upper = str(vote).upper() if isinstance(vote, str) else ""
        if vote_upper == "NEUTRAL":
            repair_notes.append("confidence missing for NEUTRAL vote — set to 0")
            return 0
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        repair_notes.append(f"confidence value {value!r} is not numeric — left as-is for retry")
        return value

    if 0.0 <= numeric <= 1.0:
        scaled = round(numeric * 100, 2)
        repair_notes.append(f"confidence {numeric} scaled to {scaled}")
        return scaled

    return numeric


def _ensure_list(value: Any, field: str, repair_notes: list[str]) -> Any:
    """Ensure array fields are lists; do not invent values when missing."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        repaired = [value]
        repair_notes.append(f"{field} was string — wrapped in array")
        return repaired
    repair_notes.append(f"{field} was {type(value).__name__} — converted to array")
    return [value]


def repair_hawk_output(
    raw_text: str,
    role: str = "",
    *,
    max_raw_preview_len: int = 800,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Repair and normalize a HAWK agent's raw text output.

    Returns ``(payload, metadata)``.  ``payload`` may be ``None`` if no JSON
    object could be extracted.  ``metadata`` always contains repair trace info.
    """
    metadata: dict[str, Any] = {
        "repaired": False,
        "repair_notes": [],
        "original_parse_error": None,
        "raw_preview": _safe_truncate(raw_text, max_raw_preview_len),
    }
    repair_notes: list[str] = []

    if not raw_text or not raw_text.strip():
        metadata["original_parse_error"] = "empty output"
        return None, metadata

    payload = extract_json_object(raw_text)
    if payload is None:
        metadata["original_parse_error"] = "no JSON object found in output"
        return None, metadata

    if not isinstance(payload, dict):
        metadata["original_parse_error"] = f"parsed JSON is {type(payload).__name__}, not object"
        return None, metadata

    # Vote normalization
    original_vote = payload.get("vote")
    normalized_vote = _normalize_vote(original_vote, repair_notes)
    if normalized_vote != original_vote:
        payload["vote"] = normalized_vote

    # Confidence normalization
    original_confidence = payload.get("confidence")
    normalized_confidence = _normalize_confidence(
        original_confidence, payload.get("vote"), repair_notes
    )
    if normalized_confidence != original_confidence:
        payload["confidence"] = normalized_confidence

    # Array fields: risk_flags should exist as array.  We default to an empty
    # array when missing because it represents "no risk flags found", which is a
    # safe default and matches the prompt instruction.
    if "risk_flags" not in payload:
        repair_notes.append("risk_flags missing — set to empty array")
        payload["risk_flags"] = []
    else:
        payload["risk_flags"] = _ensure_list(
            payload["risk_flags"], "risk_flags", repair_notes
        )

    # sources_used: normalize if present; do not invent market evidence when
    # missing.  The boundary contract will enforce it downstream if required.
    if "sources_used" in payload:
        payload["sources_used"] = _ensure_list(
            payload["sources_used"], "sources_used", repair_notes
        )

    # invalidation_level: leave untouched.  The crypto handoff validator already
    # auto-repairs this from market price when safe.

    metadata["repaired"] = bool(repair_notes)
    metadata["repair_notes"] = repair_notes
    return payload, metadata


def build_hawk_repair_prompt(
    original_output: str,
    role: str = "",
    schema_hint: str | None = None,
    market_data_summary: str | None = None,
    verbosity_mode: str = "compact",
) -> str:
    """Compact retry prompt used when schema repair alone was not enough.

    Three paths:
    - Empty/whitespace output → empty-output path (Phase 6.6.A)
    - Non-empty but no usable vote → fresh-analysis mode (Phase 6.7.A)
    - Non-empty with valid vote → preserve/convert mode

    All non-empty paths include a role-specific forbidden-key block and nesting
    hints (Phase 6.7.B).  Fresh-analysis and preserve modes also include a
    role-specific compact example (Phase 6.7.C) unless schema_hint is provided.

    ``verbosity_mode`` is appended to all paths (Phase 6.9) so that the retry
    also produces minimal valid JSON rather than verbose chain-of-thought output.
    """
    from app.services.hawk_verbosity import render_verbosity_instruction as _rvi

    _verbosity_block = f"\n{_rvi(verbosity_mode)}\n"
    role_name = role or "hawk_agent"
    _schema_block = (
        f"Required JSON shape:\n{schema_hint}\n"
        if schema_hint
        else (
            "Required JSON shape:\n"
            "{\n"
            f'  "agent": "{role_name}",\n'
            '  "symbol": "<symbol from previous output or input context>",\n'
            '  "analyzed_at": "<ISO-8601 UTC timestamp>",\n'
            '  "sources_used": ["pre-fetched market data"],\n'
            '  "vote": "BULLISH" | "BEARISH" | "NEUTRAL",\n'
            '  "confidence": <number 0-100>,\n'
            '  "data_quality": "REAL_MARKET_DATA" | "PARTIAL",\n'
            '  "market_data_snapshot": {"price": <number>, "analyzed_interval": "<timeframe>"},\n'
            '  "invalidation_level": <positive number or null>,\n'
            '  "risk_flags": [],\n'
            '  "reasoning": {"role_focus": "<hawk role>", "summary": "<specific market-data reasoning>"}\n'
            "}\n"
        )
    )

    # Role-specific forbidden-key block (Phase 6.7.B)
    _extra_forbidden = _ROLE_EXTRA_FORBIDDEN.get(role, [])
    _general_forbidden_str = '"trend_direction", "analysis", "conclusion", "recommendation"'
    _extra_forbidden_str = (
        (", " + ", ".join(f'"{k}"' for k in _extra_forbidden)) if _extra_forbidden else ""
    )
    _nesting_hint = _ROLE_NESTING_HINT.get(role, 'Place role-specific analysis fields inside "reasoning".')
    _forbidden_block = (
        "FORBIDDEN top-level keys (cause CRITICAL pipeline block if present):\n"
        + _general_forbidden_str
        + _extra_forbidden_str
        + "\n"
        + _nesting_hint
        + "\n"
    )

    # Role-specific example (Phase 6.7.C); omitted when a custom schema_hint is provided
    _role_example = _HAWK_REPAIR_EXAMPLES.get(role, "") if not schema_hint else ""
    _example_block = f"\nValid JSON example for {role_name}:\n{_role_example}\n" if _role_example else ""

    # ── Path 1: empty output (Phase 6.6.A — unchanged behavior) ────────────────
    if not (original_output or "").strip():
        _md_block = f"\nMarket data:\n{market_data_summary}\n" if market_data_summary else ""
        return (
            "No previous output was produced (empty response or token ceiling hit).\n"
            "Analyze the market data below and produce a HAWK analysis in the required JSON format.\n"
            "Do not fabricate market data. Use only the fields provided below.\n"
            "Return JSON only. No markdown. No prose. No code fences. No commentary.\n"
            + _md_block
            + "\n"
            + _forbidden_block
            + "\n"
            + _schema_block
            + _verbosity_block
        )

    _md_block = f"\nMarket data context:\n{market_data_summary}\n" if market_data_summary else ""

    # Detect whether the previous output carries a valid vote (Phase 6.7.A)
    _prior_parsed = extract_json_object(original_output)
    _prior_vote = (
        str(_prior_parsed.get("vote", "")).strip().upper()
        if isinstance(_prior_parsed, dict)
        else ""
    )
    _has_usable_vote = _prior_vote in _CANONICAL_VOTES

    # ── Path 2: non-empty but no usable vote → fresh-analysis mode ─────────────
    if not _has_usable_vote:
        return (
            "The previous call did not produce a usable HAWK output (no valid vote found).\n"
            "Do not attempt to preserve or convert the previous output.\n"
            "Generate a fresh HAWK analysis using the market data provided.\n"
            "Do not fabricate market data. Do not fabricate vote. Do not fabricate invalidation_level.\n"
            "Return JSON only. No markdown. No prose. No code fences. No commentary.\n\n"
            + _forbidden_block
            + "\n"
            + _schema_block
            + _example_block
            + _md_block
            + _verbosity_block
        )

    # ── Path 3: non-empty with valid vote → preserve/convert mode ──────────────
    return (
        "The previous output could not be parsed as the required JSON contract.\n"
        "Convert the previous answer into valid JSON only.\n"
        "Do not change the decision unless the previous vote was invalid.\n"
        "Preserve vote, confidence, reasoning, risk_flags, and invalidation_level if present.\n"
        'If risk_flags is missing, include "risk_flags": [].\n'
        'If reasoning exists under analysis/conclusion/recommendation, move it under "reasoning".\n'
        "Do not use top-level trend_direction, analysis, conclusion, or recommendation.\n"
        "Use only the required top-level keys in the schema below.\n"
        "Return JSON only. No markdown. No prose. No code fences. No commentary.\n\n"
        f"Previous output:\n{_safe_truncate(original_output, 1200)}\n"
        + _md_block
        + "\n"
        + _forbidden_block
        + "\n"
        + _schema_block
        + _example_block
        + _verbosity_block
    )


def format_hawk_block_details(
    step_key: str,
    role: str,
    model: str,
    violations: list[Any],
    raw_preview: str,
    repaired: bool,
    retry_attempted: bool,
) -> str:
    """Produce a structured, safe pause_reason / error_text message for HAWK blocks."""
    missing = [v.field for v in violations if "missing" in v.reason.lower()]
    invalid = [
        f"{v.field}: {v.reason}"
        for v in violations
        if v.field not in missing and "missing" not in v.reason.lower()
    ]

    details = {
        "step": step_key,
        "role": role,
        "model": model,
        "missing_fields": missing,
        "invalid_fields": invalid,
        "repaired": repaired,
        "retry_attempted": retry_attempted,
        "raw_preview": _safe_truncate(raw_preview, 600),
    }
    try:
        return json.dumps(details, ensure_ascii=False)
    except (TypeError, ValueError):
        # Fallback if any violation object is not JSON-serializable.
        return (
            f"step={step_key} role={role} model={model} "
            f"missing={missing} invalid={invalid} "
            f"repaired={repaired} retry={retry_attempted}"
        )
