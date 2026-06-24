"""Phase W31I — tests for the disabled DEMO execution-wiring chokepoint.

These prove the AUTO_APPROVED_DEMO -> APPROVED proposal -> ExecutionService.execute path is
audited and validated but structurally DISABLED: every disposition returns placed=False /
executed=False, the module imports no exchange / DB / ExecutionService symbol, and no production
artifact can be created here.
"""

from __future__ import annotations

import ast
import inspect

from app.services.demo_auto_approval import AutoApprovalDecision
from app.services.demo_auto_approval_execution_wiring import (
    EXECUTION_SERVICE_SIGNATURE,
    REQUIRED_PROPOSAL_FIELDS,
    WIRING_NOT_APPROVED,
    WIRING_PENDING,
    WIRING_PLACEMENT_DISABLED,
    WIRING_REQUEST_INVALID,
    DemoPlacementRequest,
    build_placement_request,
    prepare_execution_wiring,
    validate_placement_request,
)

MAX_NOTIONAL = 50.0


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


def _valid_request(notional: float = 50.0) -> DemoPlacementRequest:
    return build_placement_request(
        _approved(notional=notional),
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=[61000.0, 62000.0, 63000.0],
        position_size_usdt=notional,
    )


# ── disposition matrix ───────────────────────────────────────────────────────


def test_blocked_decision_no_placement():
    out = prepare_execution_wiring(
        _blocked(), request=None, placement_enabled=False, max_notional_usdt=MAX_NOTIONAL
    )
    assert out.disposition == WIRING_NOT_APPROVED
    assert out.placed is False
    assert out.executed is False


def test_approved_place_orders_false_disabled_no_order():
    out = prepare_execution_wiring(
        _approved(),
        request=_valid_request(),
        placement_enabled=False,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.disposition == WIRING_PLACEMENT_DISABLED
    assert out.placed is False
    assert out.executed is False


def test_approved_place_orders_true_still_wiring_pending_no_order():
    # Even with the flag flipped True and a fully valid request, the ExecutionService wiring is
    # intentionally unbuilt in W31I → wiring_pending, still NO order.
    out = prepare_execution_wiring(
        _approved(),
        request=_valid_request(),
        placement_enabled=True,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.disposition == WIRING_PENDING
    assert out.placed is False
    assert out.executed is False
    assert EXECUTION_SERVICE_SIGNATURE in out.reason


def test_missing_required_fields_validation_blocked():
    # request=None models "compile/HAWK output not available" → validation fails closed.
    out = prepare_execution_wiring(
        _approved(), request=None, placement_enabled=True, max_notional_usdt=MAX_NOTIONAL
    )
    assert out.disposition == WIRING_REQUEST_INVALID
    assert out.placed is False
    assert out.executed is False


def test_invalid_direction_validation_blocked():
    req = build_placement_request(
        _approved(direction="SIDEWAYS"),
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=[61000.0],
    )
    ok, errors = validate_placement_request(req, max_notional_usdt=MAX_NOTIONAL)
    assert ok is False
    assert any("invalid_direction" in e for e in errors)
    out = prepare_execution_wiring(
        _approved(direction="SIDEWAYS"),
        request=req,
        placement_enabled=True,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.disposition == WIRING_REQUEST_INVALID
    assert out.placed is False


def test_invalid_notional_over_cap_validation_blocked():
    req = _valid_request(notional=500.0)  # over the 50 cap
    ok, errors = validate_placement_request(req, max_notional_usdt=MAX_NOTIONAL)
    assert ok is False
    assert any("notional_over_cap" in e for e in errors)
    out = prepare_execution_wiring(
        _approved(notional=500.0),
        request=req,
        placement_enabled=True,
        max_notional_usdt=MAX_NOTIONAL,
    )
    assert out.disposition == WIRING_REQUEST_INVALID
    assert out.placed is False


def test_missing_stop_loss_validation_blocked():
    req = build_placement_request(
        _approved(), entry_price=60000.0, stop_loss=0.0, take_profit=[61000.0]
    )
    ok, errors = validate_placement_request(req, max_notional_usdt=MAX_NOTIONAL)
    assert ok is False
    assert any("stop_loss" in e for e in errors)


def test_missing_take_profit_validation_blocked():
    req = build_placement_request(
        _approved(), entry_price=60000.0, stop_loss=59000.0, take_profit=[]
    )
    ok, errors = validate_placement_request(req, max_notional_usdt=MAX_NOTIONAL)
    assert ok is False
    assert any("take_profit" in e for e in errors)


def test_valid_request_passes_validation():
    ok, errors = validate_placement_request(_valid_request(), max_notional_usdt=MAX_NOTIONAL)
    assert ok is True
    assert errors == []


def test_builder_never_invents_numbers():
    # The builder only carries the numbers it is given; symbol/direction come from the decision.
    req = build_placement_request(
        _approved(symbol="ETHUSDT", direction="SHORT"),
        entry_price=3000.0,
        stop_loss=3100.0,
        take_profit=[2900.0, 2800.0],
        position_size_usdt=25.0,
    )
    assert req.symbol == "ETHUSDT"
    assert req.direction == "SHORT"
    assert req.entry_price == 3000.0
    assert req.stop_loss == 3100.0
    assert req.take_profit == (2900.0, 2800.0)
    assert req.position_size_usdt == 25.0


# ── structural guarantees: the module cannot reach an order ──────────────────


def test_required_proposal_fields_documented():
    for f in ("symbol", "direction", "entry_plan", "stop_loss", "take_profit", "status"):
        assert f in REQUIRED_PROPOSAL_FIELDS


def test_module_imports_no_exchange_or_executionservice():
    # Static guarantee: the wiring module never imports the exchange adapter, the DB session, or
    # ExecutionService — so it is structurally incapable of placing an order or writing a row.
    import app.services.demo_auto_approval_execution_wiring as mod

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


def test_no_disposition_ever_places_or_executes():
    # Exhaustive: across every disposition, placed and executed are always False.
    cases = [
        prepare_execution_wiring(
            _blocked(), request=None, placement_enabled=False, max_notional_usdt=MAX_NOTIONAL
        ),
        prepare_execution_wiring(
            _blocked(), request=None, placement_enabled=True, max_notional_usdt=MAX_NOTIONAL
        ),
        prepare_execution_wiring(
            _approved(), request=None, placement_enabled=True, max_notional_usdt=MAX_NOTIONAL
        ),
        prepare_execution_wiring(
            _approved(),
            request=_valid_request(),
            placement_enabled=False,
            max_notional_usdt=MAX_NOTIONAL,
        ),
        prepare_execution_wiring(
            _approved(),
            request=_valid_request(),
            placement_enabled=True,
            max_notional_usdt=MAX_NOTIONAL,
        ),
    ]
    assert all(c.placed is False for c in cases)
    assert all(c.executed is False for c in cases)
