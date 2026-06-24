"""Phase W31J — one-order DEMO execution readiness gate (mock/disabled, no order).

W31E built the guarded auto-approval *decision*; W31G added the placement chokepoint; W31H made
the multi-tick READY confirmation durable; W31I audited the canonical execution path and added a
DISABLED execution-wiring chokepoint. The remaining question before a future, owner-approved
*one-order* DEMO phase (W31K) is purely diagnostic:

    "Are ALL readiness gates simultaneously satisfied, and IF they were, exactly how would the
     single order be routed — and why is no order placed in this phase regardless?"

This module answers that with a PURE readiness summary. It:
  * folds the live W29 posture, durable READY confirmation count, the auto-approval decision, an
    optional candidate placement request, and the placement flag into a structured verdict;
  * proves the ONLY future placement route is ``ExecutionService.execute`` (re-exported from the
    W31I audit module) and that the wiring layer never touches the exchange adapter;
  * is structurally incapable of placing an order: no DB / exchange / ExecutionService import, no
    I/O, every code path returns ``placed=False`` / ``executed=False`` and
    ``no_order_because_disabled=True``.

It NEVER arms placement. Even when every readiness gate is green, ``one_order_demo_armed`` is a
*diagnostic* flag describing gate state — it is not an execution trigger. Actually placing the one
order remains a separate, owner-approved W31K step gated behind ``AUTO_APPROVAL_PLACE_ORDERS=true``
AND the (still unbuilt) decision -> APPROVED-proposal -> ExecutionService.execute wiring.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.services.demo_auto_approval import AutoApprovalDecision
from app.services.demo_auto_approval_execution_wiring import (
    EXECUTION_SERVICE_SIGNATURE,
    DemoPlacementRequest,
    validate_placement_request,
)

logger = logging.getLogger(__name__)

# Grep-able log markers (mirror the W31E/W31G/W31H/W31I convention).
READINESS_GATE_MARKER = "W31J_READINESS_GATE"
W29_NOT_READY_HOLD_MARKER = "W31J_W29_NOT_READY_HOLD"
W29_READY_NO_ORDER_MARKER = "W31J_W29_READY_NO_ORDER"
ONE_ORDER_DEMO_NOT_ARMED_MARKER = "W31J_ONE_ORDER_DEMO_NOT_ARMED"

# Readiness verdicts (the answer to "could a later W31K one-order DEMO phase be considered?").
VERDICT_W29_NOT_READY = "w29_not_ready_no_order_phase"
VERDICT_GATES_INCOMPLETE = "w29_ready_but_gates_incomplete_no_order"
VERDICT_GATES_COMPLETE_PLACEMENT_DISABLED = "all_gates_complete_placement_still_disabled_no_order"


def _ready_candidate_count(posture: dict) -> int:
    return len([c for c in posture.get("candidates", []) if c.get("posture") == "READY"])


@dataclass(frozen=True)
class OneOrderReadinessSummary:
    """Diagnostic readiness verdict for a future one-order DEMO attempt. PURE DATA.

    ``placed`` / ``executed`` are ALWAYS False and ``no_order_because_disabled`` is ALWAYS True:
    holding this object, in any field combination, neither places an order nor authorises one.
    """

    # The nine readiness signals required by the W31J spec.
    w29_ready: bool
    ready_confirmed: bool
    exactly_one_symbol: bool
    placement_flag_enabled: bool
    request_available: bool
    request_valid: bool
    execution_service_path_available: bool
    would_call_execution_service_in_future: bool
    no_order_because_disabled: bool

    # Derived diagnostics.
    one_order_demo_armed: bool
    verdict: str
    execution_service_signature: str
    placed: bool = False
    executed: bool = False
    symbol: str | None = None
    direction: str | None = None
    notional_usdt: float | None = None
    ready_confirmations: int = 0
    required_confirmations: int = 0
    validation_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "marker": READINESS_GATE_MARKER,
            "w29_ready": self.w29_ready,
            "ready_confirmed": self.ready_confirmed,
            "exactly_one_symbol": self.exactly_one_symbol,
            "placement_flag_enabled": self.placement_flag_enabled,
            "request_available": self.request_available,
            "request_valid": self.request_valid,
            "execution_service_path_available": self.execution_service_path_available,
            "would_call_execution_service_in_future": self.would_call_execution_service_in_future,
            "no_order_because_disabled": self.no_order_because_disabled,
            "one_order_demo_armed": self.one_order_demo_armed,
            "verdict": self.verdict,
            "execution_service_signature": self.execution_service_signature,
            "placed": self.placed,
            "executed": self.executed,
            "symbol": self.symbol,
            "direction": self.direction,
            "notional_usdt": self.notional_usdt,
            "ready_confirmations": self.ready_confirmations,
            "required_confirmations": self.required_confirmations,
            "validation_errors": list(self.validation_errors),
        }


def summarize_one_order_readiness(
    decision: AutoApprovalDecision,
    *,
    posture: dict,
    ready_confirmations: int,
    required_confirmations: int,
    request: DemoPlacementRequest | None,
    placement_enabled: bool,
    max_notional_usdt: float,
) -> OneOrderReadinessSummary:
    """Fold the live readiness signals into a structured, logged verdict. NEVER places an order.

    Performs no I/O and imports no DB / exchange / ExecutionService symbol, so it is structurally
    incapable of placing an order or writing a row. ``no_order_because_disabled`` is always True:
    W31J is a readiness *gate*, not an execution phase.

    The two future-facing flags assert the design contract, not an action:
      * ``execution_service_path_available`` — the canonical ``ExecutionService.execute`` entrypoint
        exists and is the SOLE sanctioned route (the wiring layer never imports the adapter).
      * ``would_call_execution_service_in_future`` — a future armed W31K attempt WOULD route through
        that entrypoint (never the exchange adapter directly).
    """
    overall = posture.get("overall_posture")
    w29_ready = overall == "READY"
    exactly_one_symbol = _ready_candidate_count(posture) == 1
    ready_confirmed = ready_confirmations >= required_confirmations
    request_available = request is not None
    request_valid, validation_errors = validate_placement_request(
        request, max_notional_usdt=max_notional_usdt
    )

    # All readiness gates that a future W31K one-order attempt requires. Even when all are True,
    # this is a DIAGNOSTIC verdict — it does not place or authorise an order in W31J.
    one_order_demo_armed = all(
        (
            w29_ready,
            ready_confirmed,
            exactly_one_symbol,
            placement_enabled,
            request_available,
            request_valid,
        )
    )

    if not w29_ready:
        verdict = VERDICT_W29_NOT_READY
    elif one_order_demo_armed:
        # Gate-complete is only reachable with placement_flag_enabled True; this phase keeps the
        # flag False, so this branch is exercised by tests/mocks only — and still NO order.
        verdict = VERDICT_GATES_COMPLETE_PLACEMENT_DISABLED
    else:
        verdict = VERDICT_GATES_INCOMPLETE

    summary = OneOrderReadinessSummary(
        w29_ready=w29_ready,
        ready_confirmed=ready_confirmed,
        exactly_one_symbol=exactly_one_symbol,
        placement_flag_enabled=placement_enabled,
        request_available=request_available,
        request_valid=request_valid,
        # The path exists and is the only sanctioned route; the wiring TO it is intentionally
        # unbuilt (W31I left it execution_service_wiring_pending), which is why no order can occur.
        execution_service_path_available=True,
        would_call_execution_service_in_future=True,
        no_order_because_disabled=True,
        one_order_demo_armed=one_order_demo_armed,
        verdict=verdict,
        execution_service_signature=EXECUTION_SERVICE_SIGNATURE,
        symbol=decision.symbol,
        direction=decision.direction,
        notional_usdt=decision.notional_usdt,
        ready_confirmations=ready_confirmations,
        required_confirmations=required_confirmations,
        validation_errors=validation_errors,
    )

    payload = json.dumps(summary.as_dict(), default=str)
    if not w29_ready:
        logger.info(
            "%s overall_posture=%s — no order phase. %s",
            W29_NOT_READY_HOLD_MARKER,
            overall,
            payload,
        )
    else:
        logger.info(
            "%s symbol=%s — W29 READY observed; W31J is a readiness gate, NO order placed. %s",
            W29_READY_NO_ORDER_MARKER,
            summary.symbol,
            payload,
        )
    if not one_order_demo_armed:
        logger.info(
            "%s armed=False placement_flag=%s — one-order DEMO attempt remains gated (W31K, "
            "owner-approved, route via %s only). %s",
            ONE_ORDER_DEMO_NOT_ARMED_MARKER,
            placement_enabled,
            EXECUTION_SERVICE_SIGNATURE,
            payload,
        )
    return summary
