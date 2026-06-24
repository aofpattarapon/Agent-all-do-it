from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.execution_preflight import (
    ExecutionPreflightError,
    derive_close_side,
    derive_entry_side,
    prepare_execution_plan,
    validate_directional_risk_levels,
)


def _result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


def _proposal(direction: str = "LONG") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        symbol="BTCUSDT",
        direction=direction,
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        entry_plan={"primary_entry": 100000.0},
        take_profit=[{"tp_level": 102000.0}],
        stop_loss=99000.0,
        position_size_usdt=40.0,
    )


@pytest.mark.anyio
async def test_prepare_execution_plan_uses_latest_market_regime_and_adjusted_size() -> None:
    proposal = _proposal()
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_result(None), _result(None), _result("RISK_ON")])
    )

    with (
        patch(
            "app.services.execution_preflight.validate_order_request",
            AsyncMock(return_value={"passed": True, "errors": []}),
        ),
        patch("app.services.execution_preflight.KillSwitch") as mock_kill_switch,
        patch("app.services.execution_preflight.os.getenv") as mock_getenv,
    ):
        # Pin spot so amount precision (8dp) is deterministic regardless of ambient MARKET_TYPE.
        mock_getenv.side_effect = lambda key, default=None: (
            "spot" if key == "MARKET_TYPE" else default
        )
        ks_instance = MagicMock()
        ks_instance.check = AsyncMock(
            return_value=SimpleNamespace(
                passed=True,
                blocked_reasons=[],
                adjusted_position_size_usdt=25.0,
                consecutive_loss_ack_used=False,
            )
        )
        mock_kill_switch.return_value = ks_instance

        plan = await prepare_execution_plan(
            db=db,
            project_id=uuid4(),
            proposal=proposal,
            require_status="APPROVED",
        )

    assert plan.market_regime == "RISK_ON"
    assert plan.size_usdt == 25.0
    assert plan.side == "buy"
    assert plan.amount == round(25.0 / 100000.0, 8)
    ks_instance.check.assert_awaited_once()
    assert ks_instance.check.await_args.kwargs["market_regime"] == "RISK_ON"


@pytest.mark.anyio
async def test_prepare_execution_plan_rejects_spot_short() -> None:
    proposal = _proposal(direction="SHORT")
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_result(None), _result(None), _result("NEUTRAL")])
    )

    with (
        patch(
            "app.services.execution_preflight.validate_order_request",
            AsyncMock(return_value={"passed": True, "errors": []}),
        ),
        patch("app.services.execution_preflight.KillSwitch") as mock_kill_switch,
        patch("app.services.execution_preflight.os.getenv") as mock_getenv,
    ):
        ks_instance = MagicMock()
        ks_instance.check = AsyncMock(
            return_value=SimpleNamespace(
                passed=True,
                blocked_reasons=[],
                adjusted_position_size_usdt=None,
                consecutive_loss_ack_used=False,
            )
        )
        mock_kill_switch.return_value = ks_instance
        mock_getenv.side_effect = lambda key, default=None: (
            "spot" if key == "MARKET_TYPE" else default
        )

        with pytest.raises(
            ExecutionPreflightError, match="spot market does not support opening SHORT positions"
        ):
            await prepare_execution_plan(
                db=db,
                project_id=uuid4(),
                proposal=proposal,
                require_status="APPROVED",
            )


@pytest.mark.anyio
async def test_validate_order_request_requires_quote_notional_for_spot_buy_market() -> None:
    from app.agents.tools import exchange_tool

    with (
        patch.object(exchange_tool, "MARKET_TYPE", "spot"),
        patch.object(exchange_tool, "EXCHANGE_MODE", "paper"),
    ):
        result = await exchange_tool.validate_order_request(
            symbol="BTCUSDT",
            side="buy",
            amount=0.001,
            order_type="market",
            notional_usdt=None,
        )

    assert result["passed"] is False
    assert "quoteOrderQty" in " | ".join(result["errors"])


# ── Directional risk-level contract (pure unit) ──────────────────────────────


def test_derive_sides_are_direction_aware() -> None:
    assert derive_entry_side("LONG") == "buy"
    assert derive_entry_side("SHORT") == "sell"
    assert derive_close_side("LONG") == "sell"
    assert derive_close_side("SHORT") == "buy"


# PASS cases (1-5)
def test_validate_long_with_ascending_tps_above_entry_passes() -> None:
    assert validate_directional_risk_levels("LONG", 100.0, 95.0, [105.0, 110.0, 115.0]) == []


def test_validate_short_with_descending_tps_below_entry_passes() -> None:
    assert validate_directional_risk_levels("SHORT", 100.0, 105.0, [95.0, 90.0, 85.0]) == []


def test_validate_long_single_tp_above_entry_passes() -> None:
    assert validate_directional_risk_levels("LONG", 100.0, 90.0, [110.0]) == []


def test_validate_short_single_tp_below_entry_passes() -> None:
    assert validate_directional_risk_levels("SHORT", 100.0, 110.0, [90.0]) == []


def test_validate_long_equal_spaced_ascending_tps_passes() -> None:
    assert validate_directional_risk_levels("LONG", 100.0, 95.0, [102.0, 104.0, 106.0]) == []


# FAIL cases (6-10)
def test_validate_short_stop_loss_below_entry_returns_invalid_short_stop_loss() -> None:
    errors = validate_directional_risk_levels("SHORT", 1677.92, 1620.0, [1585.0, 1550.0, 1515.0])
    assert any(e.startswith("invalid_short_stop_loss") for e in errors)


def test_validate_long_stop_loss_above_entry_returns_invalid_long_stop_loss() -> None:
    errors = validate_directional_risk_levels("LONG", 100.0, 105.0, [110.0])
    assert any(e.startswith("invalid_long_stop_loss") for e in errors)


def test_validate_short_take_profit_above_entry_returns_invalid_short_take_profit() -> None:
    errors = validate_directional_risk_levels("SHORT", 100.0, 110.0, [95.0, 105.0])
    assert any(e.startswith("invalid_short_take_profit") for e in errors)


def test_validate_long_unordered_tps_returns_take_profits_not_ordered() -> None:
    errors = validate_directional_risk_levels("LONG", 100.0, 95.0, [110.0, 105.0])
    assert any(e.startswith("take_profits_not_ordered") for e in errors)


def test_validate_neutral_direction_returns_invalid_direction() -> None:
    errors = validate_directional_risk_levels("NEUTRAL", 100.0, 95.0, [110.0])
    assert any(e.startswith("invalid_direction") for e in errors)


# Phase 6.14.R — stop_loss == entry must block (strict inequality, fail-closed)
def test_validate_short_stop_loss_equal_to_entry_blocks() -> None:
    """The 6.14.N2 failure mode: SHORT with stop_loss == reference price must be rejected."""
    errors = validate_directional_risk_levels(
        "SHORT", 63266.8, 63266.8, [62000.0, 61000.0, 60000.0]
    )
    assert any(e.startswith("invalid_short_stop_loss") for e in errors), (
        "SHORT with stop_loss == entry must be hard-blocked (strict > required)"
    )


def test_validate_short_stop_loss_above_entry_passes_geometry() -> None:
    errors = validate_directional_risk_levels("SHORT", 100.0, 101.0, [98.0, 96.0, 94.0])
    assert not any(e.startswith("invalid_short_stop_loss") for e in errors), (
        "SHORT with stop_loss strictly above entry must pass the SL geometry check"
    )


def test_validate_long_stop_loss_equal_to_entry_blocks() -> None:
    errors = validate_directional_risk_levels("LONG", 63266.8, 63266.8, [64000.0, 65000.0, 66000.0])
    assert any(e.startswith("invalid_long_stop_loss") for e in errors), (
        "LONG with stop_loss == entry must be hard-blocked (strict < required)"
    )


def test_validate_long_stop_loss_below_entry_passes_geometry() -> None:
    errors = validate_directional_risk_levels("LONG", 100.0, 99.0, [102.0, 104.0, 106.0])
    assert not any(e.startswith("invalid_long_stop_loss") for e in errors), (
        "LONG with stop_loss strictly below entry must pass the SL geometry check"
    )


@pytest.mark.anyio
async def test_prepare_execution_plan_blocks_short_stop_loss_below_entry() -> None:
    """Smoke test for the exact ETHUSDT SHORT bug: SL placed below entry must hard-block."""
    proposal = SimpleNamespace(
        id=uuid4(),
        symbol="ETHUSDT",
        direction="SHORT",
        status="APPROVED",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        entry_plan={"primary_entry": 1677.92},
        take_profit=[{"tp_level": 1585.0}, {"tp_level": 1550.0}, {"tp_level": 1515.0}],
        stop_loss=1620.0,
        position_size_usdt=40.0,
    )
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[_result(None), _result(None), _result("NEUTRAL")])
    )

    with (
        patch(
            "app.services.execution_preflight.validate_order_request",
            AsyncMock(return_value={"passed": True, "errors": []}),
        ),
        patch("app.services.execution_preflight.KillSwitch") as mock_kill_switch,
    ):
        ks_instance = MagicMock()
        ks_instance.check = AsyncMock(
            return_value=SimpleNamespace(
                passed=True,
                blocked_reasons=[],
                adjusted_position_size_usdt=None,
                consecutive_loss_ack_used=False,
            )
        )
        mock_kill_switch.return_value = ks_instance

        with pytest.raises(ExecutionPreflightError, match="invalid_short_stop_loss"):
            await prepare_execution_plan(
                db=db,
                project_id=uuid4(),
                proposal=proposal,
                require_status="APPROVED",
            )
