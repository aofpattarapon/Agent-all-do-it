"""Phase W31G — tests for the placement chokepoint (prepare_placement).

These prove the second, independent gate on top of the policy decision:
no disposition in the W31G build ever results in an order, and AUTO_APPROVAL_PLACE_ORDERS=false
short-circuits an approved decision to PLACEMENT_DISABLED.
"""

from __future__ import annotations

from app.services.demo_auto_approval import (
    PLACEMENT_DISABLED,
    PLACEMENT_NOT_APPROVED,
    PLACEMENT_WIRING_PENDING,
    AutoApprovalDecision,
    prepare_placement,
)


def _approved() -> AutoApprovalDecision:
    return AutoApprovalDecision(
        outcome="AUTO_APPROVED_DEMO",
        reason="all_guards_passed",
        symbol="SOLUSDT",
        direction="LONG",
        notional_usdt=50.0,
    )


def _blocked() -> AutoApprovalDecision:
    return AutoApprovalDecision(outcome="BLOCKED", reason="not_ready")


def test_blocked_decision_yields_not_approved_no_order():
    out = prepare_placement(_blocked(), placement_enabled=True)
    assert out.placed is False
    assert out.disposition == PLACEMENT_NOT_APPROVED


def test_approved_but_place_orders_false_is_disabled_no_order():
    out = prepare_placement(_approved(), placement_enabled=False)
    assert out.placed is False
    assert out.disposition == PLACEMENT_DISABLED
    assert out.symbol == "SOLUSDT"


def test_approved_with_place_orders_true_is_wiring_pending_no_order():
    # Even with the flag flipped True, the W31G build must NOT place an order.
    out = prepare_placement(_approved(), placement_enabled=True)
    assert out.placed is False
    assert out.disposition == PLACEMENT_WIRING_PENDING


def test_no_disposition_ever_places_an_order():
    for decision, place in (
        (_blocked(), False),
        (_blocked(), True),
        (_approved(), False),
        (_approved(), True),
    ):
        assert prepare_placement(decision, placement_enabled=place).placed is False


def test_outcome_as_dict_is_serializable_and_marks_no_order():
    out = prepare_placement(_approved(), placement_enabled=False)
    d = out.as_dict()
    assert d["placed"] is False
    assert d["placement_marker"] == "W31G_PLACEMENT"
    assert d["disposition"] == PLACEMENT_DISABLED


def test_prepare_placement_imports_no_exchange_adapter():
    # The chokepoint module must remain pure: no exchange/adapter symbol leaks into it.
    import app.services.demo_auto_approval as mod

    assert not hasattr(mod, "BinanceFuturesAdapter")
    assert "exchange" not in {n.lower() for n in dir(mod) if not n.startswith("_")}
