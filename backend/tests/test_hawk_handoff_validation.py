from __future__ import annotations

import json

from app.services.crypto_handoff_validator import validate_hawk_output, validate_step_output
from app.services.handoff_contracts import contracts_for_handoff, validate_handoff


def _valid_hawk_payload(role: str = "hawk_trend") -> dict:
    return {
        "agent": role,
        "symbol": "BTCUSDT",
        "analyzed_at": "2026-06-15T00:00:00Z",
        "sources_used": ["pre-fetched market data"],
        "vote": "BULLISH",
        "confidence": 72,
        "data_quality": "REAL_MARKET_DATA",
        "market_data_snapshot": {"price": 65000.0, "analyzed_interval": "4h"},
        "invalidation_level": 64000.0,
        "risk_flags": [],
        "reasoning": "EMA alignment, MACD, and recent_candles support a bullish vote.",
    }


def test_hawk_validator_blocks_qwen_analysis_shape_without_vote_confidence() -> None:
    payload = {
        "trend_direction": "bullish",
        "analysis": {"ema_alignment": "price above short EMAs"},
        "conclusion": "trend is improving",
        "invalidation_level": 64000.0,
    }

    valid, violations = validate_step_output(
        "hawk_trend", payload, {"_market_price": 65000.0}
    )

    assert valid is False
    assert any(v.field == "vote" and v.critical for v in violations)
    assert any(v.field == "confidence" for v in violations)


def test_hawk_validator_rejects_forbidden_top_level_trend_direction() -> None:
    payload = {
        **_valid_hawk_payload("hawk_trend"),
        "trend_direction": "SIDEWAYS",
    }

    valid, violations = validate_step_output(
        "hawk_trend", payload, {"_market_price": 65000.0}
    )

    assert valid is False
    assert any(v.field == "trend_direction" and v.critical for v in violations)


def test_hawk_validator_rejects_forbidden_top_level_analysis_conclusion_recommendation() -> None:
    payload = {
        **_valid_hawk_payload("hawk_counter"),
        "analysis": {"rsi": "overbought"},
        "conclusion": "counter trend risk exists",
        "recommendation": "consider short",
    }

    valid, violations = validate_step_output(
        "hawk_counter", payload, {"_market_price": 65000.0}
    )

    assert valid is False
    assert {v.field for v in violations if v.critical} >= {
        "analysis",
        "conclusion",
        "recommendation",
    }


def test_hawk_validator_rejects_missing_risk_flags_without_repair() -> None:
    payload = _valid_hawk_payload("hawk_counter")
    payload.pop("risk_flags")

    valid, violations = validate_step_output(
        "hawk_counter", payload, {"_market_price": 65000.0}
    )

    assert valid is False
    assert any(v.field == "risk_flags" and v.critical for v in violations)


def test_hawk_validator_rejects_non_list_risk_flags_without_repair() -> None:
    payload = {
        **_valid_hawk_payload("hawk_counter"),
        "risk_flags": "overbought",
    }

    valid, violations = validate_step_output(
        "hawk_counter", payload, {"_market_price": 65000.0}
    )

    assert valid is False
    assert any(v.field == "risk_flags" and v.critical for v in violations)


def test_hawk_validator_blocks_structure_risk_only_payload_without_vote_confidence() -> None:
    payload = {
        "risk_flags": [],
        "invalidation_level": 68633.12,
        "_invalidation_repaired": True,
    }

    valid, violations = validate_step_output(
        "hawk_structure", payload, {"_market_price": 66634.1}
    )

    assert valid is False
    assert any(v.field == "vote" and v.critical for v in violations)
    assert any(v.field == "confidence" for v in violations)


def test_hawk_validator_accepts_required_schema_payload() -> None:
    valid, violations = validate_step_output(
        "hawk_trend", _valid_hawk_payload("hawk_trend"), {"_market_price": 65000.0}
    )

    assert valid is True
    assert violations == []


# ── Phase 6.6.D: NEUTRAL invalidation_level auto-repair restricted ──────────


def test_neutral_invalidation_level_not_fabricated() -> None:
    payload: dict = {"vote": "NEUTRAL", "confidence": 35, "risk_flags": []}
    violations = validate_hawk_output(payload, "hawk_counter", market_price=66036.6)
    assert "_invalidation_repaired" not in payload
    assert payload.get("invalidation_level") is None


def test_neutral_null_invalidation_creates_non_blocking_warning() -> None:
    payload: dict = {"vote": "NEUTRAL", "confidence": 35, "risk_flags": []}
    violations = validate_hawk_output(payload, "hawk_counter", market_price=66036.6)
    inv_violations = [v for v in violations if v.field == "invalidation_level"]
    assert len(inv_violations) == 1
    assert inv_violations[0].critical is False
    assert "not required" in inv_violations[0].reason or "skipping auto-repair" in inv_violations[0].reason


def test_neutral_invalidation_warning_without_market_price() -> None:
    payload: dict = {"vote": "NEUTRAL", "confidence": 40, "risk_flags": []}
    violations = validate_hawk_output(payload, "hawk_counter", market_price=None)
    inv_violations = [v for v in violations if v.field == "invalidation_level"]
    assert len(inv_violations) == 1
    assert inv_violations[0].critical is False
    assert "_invalidation_repaired" not in payload


def test_bullish_null_invalidation_still_auto_repaired() -> None:
    payload: dict = {"vote": "BULLISH", "confidence": 70, "risk_flags": []}
    validate_hawk_output(payload, "hawk_trend", market_price=66000.0)
    assert payload.get("_invalidation_repaired") is True
    assert payload.get("invalidation_level") == round(66000.0 * 0.97, 2)


def test_bearish_null_invalidation_still_auto_repaired() -> None:
    payload: dict = {"vote": "BEARISH", "confidence": 65, "risk_flags": []}
    validate_hawk_output(payload, "hawk_structure", market_price=66000.0)
    assert payload.get("_invalidation_repaired") is True
    assert payload.get("invalidation_level") == round(66000.0 * 1.03, 2)


def test_bullish_null_invalidation_no_price_is_critical() -> None:
    payload: dict = {"vote": "BULLISH", "confidence": 70, "risk_flags": []}
    violations = validate_hawk_output(payload, "hawk_trend", market_price=None)
    inv_violations = [v for v in violations if v.field == "invalidation_level"]
    assert any(v.critical for v in inv_violations)
    assert "_invalidation_repaired" not in payload


def test_valid_invalidation_level_not_touched_for_any_vote() -> None:
    for vote in ("BULLISH", "BEARISH", "NEUTRAL"):
        payload: dict = {"vote": vote, "confidence": 60, "risk_flags": [], "invalidation_level": 64000.0}
        validate_hawk_output(payload, "hawk_trend", market_price=66000.0)
        assert payload["invalidation_level"] == 64000.0
        assert "_invalidation_repaired" not in payload


def test_neutral_valid_invalidation_level_preserved() -> None:
    payload: dict = {"vote": "NEUTRAL", "confidence": 40, "risk_flags": [], "invalidation_level": 65000.0}
    violations = validate_hawk_output(payload, "hawk_counter", market_price=66000.0)
    assert payload["invalidation_level"] == 65000.0
    inv_violations = [v for v in violations if v.field == "invalidation_level"]
    assert inv_violations == []


def test_hawk_validator_accepts_required_structure_schema_payload() -> None:
    valid, violations = validate_step_output(
        "hawk_structure",
        {
            **_valid_hawk_payload("hawk_structure"),
            "reasoning": {
                "role_focus": "structure",
                "support": [64000.0],
                "resistance": [67000.0],
                "vwap_position": "price is above VWAP",
            },
        },
        {"_market_price": 65000.0},
    )

    assert valid is True
    assert violations == []


def test_hawk_validator_accepts_trend_assessment_inside_reasoning() -> None:
    valid, violations = validate_step_output(
        "hawk_trend",
        {
            **_valid_hawk_payload("hawk_trend"),
            "reasoning": {
                "role_focus": "trend",
                "trend_assessment": {
                    "direction": "SIDEWAYS",
                    "ema_alignment": "mixed",
                    "price_structure": "ranging",
                    "macd": "neutral",
                },
            },
        },
        {"_market_price": 65000.0},
    )

    assert valid is True
    assert violations == []


def test_hawk_validator_accepts_counter_with_empty_risk_flags() -> None:
    valid, violations = validate_step_output(
        "hawk_counter",
        {
            **_valid_hawk_payload("hawk_counter"),
            "vote": "NEUTRAL",
            "confidence": 35,
            "risk_flags": [],
            "reasoning": {
                "role_focus": "counter",
                "counter_assessment": {"summary": "no clear counter-trend risk"},
            },
        },
        {"_market_price": 65000.0},
    )

    assert valid is True
    assert violations == []


def test_hawk_boundary_contract_accepts_required_schema_payload() -> None:
    contract = contracts_for_handoff("hawk_trend", "hawk_vote_gate")[0]

    result = validate_handoff(json.dumps(_valid_hawk_payload("hawk_trend")), contract)

    assert result.passed is True
    assert result.missing_fields == ()
    assert result.parse_error is None


# ── Phase 6.10: invalidation_level is optional in hawk_to_hawk_vote_gate ────


def test_hawk_contract_neutral_null_invalidation_level_passes() -> None:
    """NEUTRAL vote with explicit invalidation_level=null must pass the contract."""
    contract = contracts_for_handoff("hawk_counter", "hawk_vote_gate")[0]
    payload = {
        **_valid_hawk_payload("hawk_counter"),
        "vote": "NEUTRAL",
        "confidence": 38,
        "invalidation_level": None,
    }
    result = validate_handoff(json.dumps(payload), contract)
    assert result.passed is True
    assert result.missing_fields == ()


def test_hawk_contract_neutral_absent_invalidation_level_passes() -> None:
    """NEUTRAL vote with invalidation_level key absent entirely must pass the contract."""
    contract = contracts_for_handoff("hawk_trend", "hawk_vote_gate")[0]
    payload = {k: v for k, v in _valid_hawk_payload("hawk_trend").items() if k != "invalidation_level"}
    payload["vote"] = "NEUTRAL"
    payload["confidence"] = 32
    result = validate_handoff(json.dumps(payload), contract)
    assert result.passed is True
    assert result.missing_fields == ()


def test_hawk_contract_bullish_with_level_still_passes() -> None:
    """BULLISH vote with a numeric invalidation_level still passes the contract."""
    contract = contracts_for_handoff("hawk_trend", "hawk_vote_gate")[0]
    result = validate_handoff(json.dumps(_valid_hawk_payload("hawk_trend")), contract)
    assert result.passed is True


def test_hawk_contract_bearish_with_level_still_passes() -> None:
    """BEARISH vote with a numeric invalidation_level still passes the contract."""
    contract = contracts_for_handoff("hawk_structure", "hawk_vote_gate")[0]
    payload = {**_valid_hawk_payload("hawk_structure"), "vote": "BEARISH", "invalidation_level": 68500.0}
    result = validate_handoff(json.dumps(payload), contract)
    assert result.passed is True


def test_hawk_contract_bullish_null_invalidation_passes_contract() -> None:
    """BULLISH with null invalidation_level passes the CONTRACT layer.

    Enforcement for directional votes happens in crypto_handoff_validator.py
    (auto-repair) and in the post-gate block — not in the contract itself.
    """
    contract = contracts_for_handoff("hawk_trend", "hawk_vote_gate")[0]
    payload = {**_valid_hawk_payload("hawk_trend"), "invalidation_level": None}
    result = validate_handoff(json.dumps(payload), contract)
    assert result.passed is True


def test_hawk_contract_missing_vote_still_fails() -> None:
    """Missing 'vote' field must still fail the contract."""
    contract = contracts_for_handoff("hawk_counter", "hawk_vote_gate")[0]
    payload = {k: v for k, v in _valid_hawk_payload("hawk_counter").items() if k != "vote"}
    result = validate_handoff(json.dumps(payload), contract)
    assert result.passed is False
    assert "vote" in result.missing_fields


def test_hawk_contract_missing_agent_still_fails() -> None:
    """Missing 'agent' field must still fail the contract."""
    contract = contracts_for_handoff("hawk_trend", "hawk_vote_gate")[0]
    payload = {k: v for k, v in _valid_hawk_payload("hawk_trend").items() if k != "agent"}
    result = validate_handoff(json.dumps(payload), contract)
    assert result.passed is False
    assert "agent" in result.missing_fields


def test_hawk_contract_missing_symbol_still_fails() -> None:
    """Missing 'symbol' field must still fail the contract."""
    contract = contracts_for_handoff("hawk_structure", "hawk_vote_gate")[0]
    payload = {k: v for k, v in _valid_hawk_payload("hawk_structure").items() if k != "symbol"}
    result = validate_handoff(json.dumps(payload), contract)
    assert result.passed is False
    assert "symbol" in result.missing_fields


def test_hawk_contract_unparseable_json_still_fails() -> None:
    """Unparseable JSON must still fail the contract."""
    contract = contracts_for_handoff("hawk_counter", "hawk_vote_gate")[0]
    result = validate_handoff("not json at all", contract)
    assert result.passed is False
    assert result.parse_error is not None


def test_hawk_contract_empty_output_still_fails() -> None:
    """Empty output must still fail the contract."""
    contract = contracts_for_handoff("hawk_trend", "hawk_vote_gate")[0]
    result = validate_handoff("", contract)
    assert result.passed is False
    assert result.parse_error is not None


def test_hawk_boundary_contract_rejects_analysis_shape_payload() -> None:
    contract = contracts_for_handoff("hawk_counter", "hawk_vote_gate")[0]
    payload = {
        "analysis": {"rsi": 71.0},
        "recommendation": {"action": "consider short"},
        "invalidation_level": 66500.0,
        "risk_flags": ["overbought"],
    }

    result = validate_handoff(json.dumps(payload), contract)

    assert result.passed is False
    assert set(result.missing_fields) >= {
        "agent",
        "symbol",
        "analyzed_at",
        "sources_used",
        "vote",
        "confidence",
        "data_quality",
        "market_data_snapshot",
    }
