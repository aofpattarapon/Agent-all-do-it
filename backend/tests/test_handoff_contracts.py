from __future__ import annotations

import json
from unittest.mock import AsyncMock

from app.services.handoff_contracts import contracts_for_handoff, validate_handoff
from app.services.run_executor import RunExecutor


def test_validate_handoff_accepts_required_fields() -> None:
    contract = contracts_for_handoff("compile_proposal", "winrate_trade_gate")[0]
    payload = json.dumps(
        {
            "approval_status": "PENDING_APPROVAL",
            "direction": "LONG",
            "entry_plan": {"primary_entry": 101234.5},
            "stop_loss": 99888.0,
            "take_profit": [102000.0, 103000.0],
            "risk_reward": 2.4,
            "position_size_usdt": 40,
            "market_type": "futures",
        }
    )

    result = validate_handoff(payload, contract)

    assert result.passed is True
    assert result.missing_fields == ()
    assert result.parse_error is None


def test_validate_handoff_reports_missing_nested_fields() -> None:
    contract = contracts_for_handoff("compile_proposal", "winrate_trade_gate")[0]
    payload = json.dumps(
        {
            "approval_status": "PENDING_APPROVAL",
            "direction": "LONG",
            "entry_plan": {},
            "stop_loss": 99888.0,
            "take_profit": [],
            "risk_reward": 2.4,
            "position_size_usdt": 40,
            "market_type": "futures",
        }
    )

    result = validate_handoff(payload, contract)

    assert result.passed is False
    assert set(result.missing_fields) == {"entry_plan.primary_entry", "take_profit"}
    assert result.parse_error is None


def test_run_executor_reports_fail_closed_boundary_message() -> None:
    executor = RunExecutor(AsyncMock())

    message = executor._evaluate_boundary_handoff(
        step_key="compile_proposal",
        next_step_key="winrate_trade_gate",
        output_text=json.dumps(
            {
                "approval_status": "PENDING_APPROVAL",
                "direction": "LONG",
                "entry_plan": {},
                "stop_loss": 99888.0,
                "take_profit": [102000.0],
                "risk_reward": 2.4,
                "position_size_usdt": 40,
            }
        ),
    )

    assert message is not None
    assert "handoff contract 'trade_proposal_to_gate_or_execute' failed".lower() in message.lower()
    assert "compile_proposal" in message
    assert "winrate_trade_gate" in message
    assert "entry_plan.primary_entry" in message
