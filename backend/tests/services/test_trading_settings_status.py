"""Tests for the read-only Trading Settings Sync order-readiness logic (Phase W32A).

Exercises the pure ``compute_order_readiness`` helper, which decides ``can_send_order_now``
fail-closed. These tests never touch the DB, the exchange, or ExecutionService.
"""

from __future__ import annotations

from app.services.trading_settings_status import compute_order_readiness

# The current W31J-PAUSE posture: W29 HOLD, placement disabled, wiring unarmed, no payload.
_PAUSE_KWARGS = {
    "w29_posture": "HOLD",
    "ready_symbol_count": 0,
    "place_orders_enabled": False,
    "ready_confirmations": 0,
    "required_confirmations": 2,
    "execution_wiring_armed": False,
    "valid_placement_request": False,
    "is_demo": True,
    "is_live": False,
}


def test_can_send_order_now_false_when_w29_hold() -> None:
    result = compute_order_readiness(**_PAUSE_KWARGS)
    assert result["can_send_order_now"] is False
    assert result["verdict"] == "w29_not_ready_no_order_phase"


def test_blockers_include_w29_hold_and_place_orders_false() -> None:
    blockers = compute_order_readiness(**_PAUSE_KWARGS)["blockers"]
    assert any("not READY" in b for b in blockers)
    assert any("PLACE_ORDERS=false" in b for b in blockers)
    assert any("wiring not armed" in b for b in blockers)


def test_all_gates_green_allows_send() -> None:
    result = compute_order_readiness(
        w29_posture="READY",
        ready_symbol_count=1,
        place_orders_enabled=True,
        ready_confirmations=2,
        required_confirmations=2,
        execution_wiring_armed=True,
        valid_placement_request=True,
        is_demo=True,
        is_live=False,
    )
    assert result["can_send_order_now"] is True
    assert result["blockers"] == []


def test_live_mode_is_blocked_even_when_other_gates_green() -> None:
    result = compute_order_readiness(
        w29_posture="READY",
        ready_symbol_count=1,
        place_orders_enabled=True,
        ready_confirmations=2,
        required_confirmations=2,
        execution_wiring_armed=True,
        valid_placement_request=True,
        is_demo=False,
        is_live=True,
    )
    assert result["can_send_order_now"] is False
    assert any("LIVE" in b for b in result["blockers"])


def test_incomplete_confirmations_block_when_w29_ready() -> None:
    result = compute_order_readiness(
        w29_posture="READY",
        ready_symbol_count=1,
        place_orders_enabled=True,
        ready_confirmations=1,
        required_confirmations=2,
        execution_wiring_armed=True,
        valid_placement_request=True,
        is_demo=True,
        is_live=False,
    )
    assert result["can_send_order_now"] is False
    assert result["verdict"] == "w29_ready_but_gates_incomplete_no_order"
    assert any("confirmations incomplete" in b for b in result["blockers"])
