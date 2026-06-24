"""Phase W31J — tests for the one-order DEMO execution readiness gate.

These prove the readiness summary is a PURE diagnostic: across every W29 posture and gate
combination it places no order, authorises no order, imports no exchange / DB / ExecutionService
symbol, and always reports ``no_order_because_disabled=True`` with ``placed``/``executed`` False.
The only future placement route it documents is ``ExecutionService.execute``.
"""

from __future__ import annotations

import ast
import inspect

from app.services.demo_auto_approval import AutoApprovalDecision
from app.services.demo_auto_approval_execution_wiring import (
    EXECUTION_SERVICE_SIGNATURE,
    build_placement_request,
)
from app.services.demo_auto_approval_readiness import (
    VERDICT_GATES_COMPLETE_PLACEMENT_DISABLED,
    VERDICT_GATES_INCOMPLETE,
    VERDICT_W29_NOT_READY,
    summarize_one_order_readiness,
)

MAX_NOTIONAL = 50.0
REQUIRED_TICKS = 2


def _approved(
    symbol: str = "BTCUSDT", direction: str = "LONG", notional: float = 50.0
) -> AutoApprovalDecision:
    return AutoApprovalDecision(
        outcome="AUTO_APPROVED_DEMO",
        reason="all_guards_passed",
        symbol=symbol,
        direction=direction,
        notional_usdt=notional,
    )


def _blocked(reason: str = "not_ready") -> AutoApprovalDecision:
    return AutoApprovalDecision(outcome="BLOCKED", reason=reason)


def _hold_posture() -> dict:
    return {
        "overall_posture": "HOLD",
        "candidates": [
            {"symbol": "BTCUSDT", "posture": "WATCH_ONLY"},
            {"symbol": "ETHUSDT", "posture": "WATCH_ONLY"},
        ],
    }


def _ready_posture(symbol: str = "BTCUSDT") -> dict:
    return {
        "overall_posture": "READY",
        "candidates": [
            {"symbol": symbol, "posture": "READY"},
            {"symbol": "ETHUSDT", "posture": "WATCH_ONLY"},
        ],
    }


def _valid_request(notional: float = 50.0):
    return build_placement_request(
        _approved(notional=notional),
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=[61000.0, 62000.0, 63000.0],
        position_size_usdt=notional,
    )


# ── W29 HOLD → readiness not armed, no order ─────────────────────────────────


def test_w29_hold_not_armed_no_order():
    out = summarize_one_order_readiness(
        _blocked(),
        posture=_hold_posture(),
        ready_confirmations=0,
        required_confirmations=REQUIRED_TICKS,
        request=None,
        placement_enabled=False,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.w29_ready is False
    assert out.one_order_demo_armed is False
    assert out.verdict == VERDICT_W29_NOT_READY
    assert out.no_order_because_disabled is True
    assert out.placed is False and out.executed is False


# ── W29 READY tick 1 → ready_not_confirmed, no order ─────────────────────────


def test_w29_ready_tick1_not_confirmed_no_order():
    out = summarize_one_order_readiness(
        _approved(),
        posture=_ready_posture(),
        ready_confirmations=1,
        required_confirmations=REQUIRED_TICKS,
        request=_valid_request(),
        placement_enabled=False,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.w29_ready is True
    assert out.ready_confirmed is False
    assert out.one_order_demo_armed is False
    assert out.verdict == VERDICT_GATES_INCOMPLETE
    assert out.no_order_because_disabled is True
    assert out.placed is False and out.executed is False


# ── W29 READY tick 2 → ready_confirmed but placement disabled, no order ──────


def test_w29_ready_tick2_confirmed_but_placement_disabled_no_order():
    out = summarize_one_order_readiness(
        _approved(),
        posture=_ready_posture(),
        ready_confirmations=2,
        required_confirmations=REQUIRED_TICKS,
        request=_valid_request(),
        placement_enabled=False,  # the hard gate stays closed
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.w29_ready is True
    assert out.ready_confirmed is True
    assert out.exactly_one_symbol is True
    assert out.request_valid is True
    assert out.placement_flag_enabled is False
    assert out.one_order_demo_armed is False  # flag gates it
    assert out.verdict == VERDICT_GATES_INCOMPLETE
    assert out.no_order_because_disabled is True
    assert out.placed is False and out.executed is False


# ── AUTO_APPROVED_DEMO + request invalid → blocked ───────────────────────────


def test_ready_request_invalid_not_armed():
    out = summarize_one_order_readiness(
        _approved(),
        posture=_ready_posture(),
        ready_confirmations=2,
        required_confirmations=REQUIRED_TICKS,
        request=None,  # no compile/HAWK output → invalid, fail closed
        placement_enabled=True,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.request_available is False
    assert out.request_valid is False
    assert out.one_order_demo_armed is False
    assert out.no_order_because_disabled is True
    assert out.placed is False and out.executed is False


# ── request missing compile_proposal fields → blocked ────────────────────────


def test_ready_request_over_cap_not_armed():
    out = summarize_one_order_readiness(
        _approved(notional=500.0),
        posture=_ready_posture(),
        ready_confirmations=2,
        required_confirmations=REQUIRED_TICKS,
        request=_valid_request(notional=500.0),  # over the 50 cap
        placement_enabled=True,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.request_valid is False
    assert any("notional_over_cap" in e for e in out.validation_errors)
    assert out.one_order_demo_armed is False
    assert out.no_order_because_disabled is True


# ── all gates green in a MOCK-only helper → still not an order phase ──────────


def test_all_gates_green_mock_only_still_no_order():
    # Simulates a FUTURE armed phase entirely in-memory: PLACE_ORDERS True + valid request +
    # confirmed READY. Even so, W31J reports no_order_because_disabled=True and never executes.
    out = summarize_one_order_readiness(
        _approved(),
        posture=_ready_posture(),
        ready_confirmations=3,
        required_confirmations=REQUIRED_TICKS,
        request=_valid_request(),
        placement_enabled=True,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.one_order_demo_armed is True  # diagnostic only
    assert out.verdict == VERDICT_GATES_COMPLETE_PLACEMENT_DISABLED
    assert out.would_call_execution_service_in_future is True
    assert out.execution_service_path_available is True
    assert out.no_order_because_disabled is True  # W31J is not an order phase
    assert out.placed is False and out.executed is False
    assert EXECUTION_SERVICE_SIGNATURE in out.execution_service_signature


# ── two READY symbols → not exactly one → not armed ──────────────────────────


def test_two_ready_symbols_not_exactly_one():
    posture = {
        "overall_posture": "READY",
        "candidates": [
            {"symbol": "BTCUSDT", "posture": "READY"},
            {"symbol": "ETHUSDT", "posture": "READY"},
        ],
    }
    out = summarize_one_order_readiness(
        _approved(),
        posture=posture,
        ready_confirmations=2,
        required_confirmations=REQUIRED_TICKS,
        request=_valid_request(),
        placement_enabled=True,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.exactly_one_symbol is False
    assert out.one_order_demo_armed is False
    assert out.no_order_because_disabled is True


# ── ExecutionService is the only documented future placement path ────────────


def test_execution_service_is_only_future_path():
    out = summarize_one_order_readiness(
        _approved(),
        posture=_ready_posture(),
        ready_confirmations=2,
        required_confirmations=REQUIRED_TICKS,
        request=_valid_request(),
        placement_enabled=True,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert "ExecutionService.execute" in out.execution_service_signature
    assert out.would_call_execution_service_in_future is True


# ── structural guarantee: no exchange / DB / ExecutionService reachable ──────


def test_module_imports_no_exchange_or_executionservice():
    import app.services.demo_auto_approval_readiness as mod

    source = inspect.getsource(mod)
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)

    banned = ("execution_service", "binance", "adapter", "exchange", "db.session", "ccxt")
    for mod_name in imported:
        assert not any(b in mod_name.lower() for b in banned), f"banned import: {mod_name}"


def test_no_combination_ever_places_or_executes():
    # Exhaustive sweep across postures / confirmations / flag / request validity: never an order.
    postures = [_hold_posture(), _ready_posture()]
    requests = [None, _valid_request(), _valid_request(notional=500.0)]
    decisions = [_blocked(), _approved()]
    for posture in postures:
        for req in requests:
            for flag in (False, True):
                for confirms in (0, 1, 2, 3):
                    for dec in decisions:
                        out = summarize_one_order_readiness(
                            dec,
                            posture=posture,
                            ready_confirmations=confirms,
                            required_confirmations=REQUIRED_TICKS,
                            request=req,
                            placement_enabled=flag,
                            max_notional_usdt=MAX_NOTIONAL,
                        )
                        assert out.placed is False
                        assert out.executed is False
                        assert out.no_order_because_disabled is True
