"""Phase W31I — disabled DEMO execution-wiring chokepoint + ExecutionService path audit.

W31E/W31F built the guarded auto-approval *decision*; W31G added the placement chokepoint
(``prepare_placement``) that proves an approval is not an order; W31H made the multi-tick READY
confirmation durable. The one remaining gap before ``AUTO_APPROVAL_PLACE_ORDERS=true`` could ever
be considered is the wiring from an ``AUTO_APPROVED_DEMO`` decision to the canonical execution
path:

    AUTO_APPROVED_DEMO decision
      -> build a guarded DEMO TradeProposal (status=APPROVED)
      -> ExecutionService.execute(proposal_id, project_id, user_id)   # the ONLY exchange path

This module *prepares and audits* that path while keeping it provably DISABLED. It:
  * documents the canonical ExecutionService signature and the minimum proposal payload a future
    armed phase would have to build (``REQUIRED_PROPOSAL_FIELDS`` / ``EXECUTION_SERVICE_SIGNATURE``);
  * provides a PURE builder (``build_placement_request``) that assembles a candidate placement
    request from a decision plus pipeline/compile-supplied numbers — it NEVER invents entry/SL/TP
    or size (those must come from ``compile_proposal`` / HAWK output, never fabricated here);
  * provides a PURE validator (``validate_placement_request``) for the required fields, direction,
    and the notional cap;
  * provides the disabled wrapper (``prepare_execution_wiring``) that returns a *disposition* only
    and is structurally incapable of placing an order: it has no DB import, no exchange import, and
    does NOT import or call ExecutionService. Every path returns ``placed=False`` / ``executed=False``.

Dispositions (none of which place an order in this build):
  * not_approved                       -> the policy already blocked; nothing to place.
  * placement_request_invalid          -> required proposal fields missing / out of cap.
  * placement_flag_disabled            -> AUTO_APPROVAL_PLACE_ORDERS is False (the hard gate). STOP.
  * execution_service_wiring_pending   -> flag True + a valid request, but the
                                          decision->APPROVED-proposal->ExecutionService.execute
                                          wiring is intentionally NOT built in W31I. STOP, no order.

Only a later, owner-reviewed phase (W31J+) may add the ``execution_service_wiring_pending`` ->
ExecutionService path, and even then it MUST route through ``ExecutionService.execute`` (never the
exchange adapter directly).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from app.services.demo_auto_approval import AutoApprovalDecision

logger = logging.getLogger(__name__)

# --- Audit constants -------------------------------------------------------------------------

# The canonical (and only) exchange-order path. Auditors should be able to read this off the
# module without grepping the codebase. The adapter is reached ONLY from inside ExecutionService.
EXECUTION_SERVICE_SIGNATURE = "ExecutionService.execute(proposal_id, project_id, user_id)"

# Minimum TradeProposal payload an armed phase must build before ExecutionService.execute will
# pass its 12 pre-checks (derived from execution_service._run_pre_checks). All numeric/plan fields
# must come from compile_proposal / HAWK output — NONE may be fabricated by the wiring layer.
REQUIRED_PROPOSAL_FIELDS = (
    "project_id",  # owner project (FK)
    "run_id",  # the real pipeline run that produced the plan (FK-like, NOT NULL)
    "symbol",  # non-empty, must exist in exchange info
    "direction",  # LONG | SHORT
    "entry_plan",  # dict carrying entry_price > 0
    "stop_loss",  # protective stop (check_9)
    "take_profit",  # non-empty TP ladder (check_10)
    "position_size_usdt",  # > 0 and within the notional cap
    "status",  # must be APPROVED (check_1)
)

# Log markers (grep-able; mirror the W31E/W31G/W31H marker convention).
EXECUTION_WIRING_AUDIT_MARKER = "W31I_EXECUTION_WIRING_AUDIT"
PLACEMENT_REQUEST_VALIDATION_MARKER = "W31I_PLACEMENT_REQUEST_VALIDATION"
EXECUTION_SERVICE_WIRING_PENDING_MARKER = "W31I_EXECUTION_SERVICE_WIRING_PENDING"
NO_ORDER_PLACE_ORDERS_FALSE_MARKER = "W31I_NO_ORDER_PLACE_ORDERS_FALSE"

# Dispositions.
WIRING_NOT_APPROVED = "not_approved"
WIRING_REQUEST_INVALID = "placement_request_invalid"
WIRING_PLACEMENT_DISABLED = "placement_flag_disabled"
WIRING_PENDING = "execution_service_wiring_pending"


@dataclass(frozen=True)
class DemoPlacementRequest:
    """Candidate placement request — the in-memory shape of the proposal a future armed phase
    would persist as an APPROVED TradeProposal. PURE DATA: holding one cannot place an order.

    Every field is supplied by the caller from decision + compile/HAWK output. This object never
    derives or fabricates entry/SL/TP/size; missing inputs simply make it fail validation.
    """

    symbol: str
    direction: str
    position_size_usdt: float
    entry_price: float
    stop_loss: float
    take_profit: tuple[float, ...]
    expires_at: datetime | None = None

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "position_size_usdt": self.position_size_usdt,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": list(self.take_profit),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


def build_placement_request(
    decision: AutoApprovalDecision,
    *,
    entry_price: float,
    stop_loss: float,
    take_profit: list[float] | tuple[float, ...],
    position_size_usdt: float | None = None,
    expires_at: datetime | None = None,
) -> DemoPlacementRequest:
    """Assemble a candidate placement request from a decision + pipeline-supplied numbers.

    PURE. ``symbol``/``direction`` come from the decision; ``entry_price``/``stop_loss``/
    ``take_profit`` MUST be supplied by the caller from compile_proposal / HAWK output and are
    never invented here. ``position_size_usdt`` defaults to the decision's auto-approved notional.
    Assembling a request neither validates it nor places anything.
    """
    notional = (
        position_size_usdt if position_size_usdt is not None else (decision.notional_usdt or 0.0)
    )
    return DemoPlacementRequest(
        symbol=str(decision.symbol or ""),
        direction=str(decision.direction or ""),
        position_size_usdt=float(notional),
        entry_price=float(entry_price),
        stop_loss=float(stop_loss),
        take_profit=tuple(float(tp) for tp in take_profit),
        expires_at=expires_at,
    )


def validate_placement_request(
    request: DemoPlacementRequest | None, *, max_notional_usdt: float
) -> tuple[bool, list[str]]:
    """Validate the required proposal fields, direction, and notional cap. PURE.

    Returns ``(ok, errors)``. Mirrors the relevant subset of ExecutionService pre-checks so a
    future armed phase can fail fast before ever building a DB row. Fails closed: a ``None``
    request (fields not produced by the pipeline) is invalid.
    """
    errors: list[str] = []
    if request is None:
        errors.append("placement_request_unavailable: no compile/HAWK output to build from")
        logger.info("%s ok=False errors=%s", PLACEMENT_REQUEST_VALIDATION_MARKER, errors)
        return False, errors

    if request.direction.upper() not in {"LONG", "SHORT"}:
        errors.append(f"invalid_direction: {request.direction or '<empty>'}")
    if not request.symbol.strip():
        errors.append("missing_symbol")
    if request.entry_price <= 0:
        errors.append("invalid_entry_price: must be > 0")
    if request.stop_loss <= 0:
        errors.append("missing_or_invalid_stop_loss")
    if not request.take_profit or any(tp <= 0 for tp in request.take_profit):
        errors.append("missing_or_invalid_take_profit")
    if request.position_size_usdt <= 0:
        errors.append("invalid_notional: position_size_usdt must be > 0")
    elif request.position_size_usdt > max_notional_usdt:
        errors.append(f"notional_over_cap: {request.position_size_usdt} > max {max_notional_usdt}")

    ok = not errors
    logger.info(
        "%s ok=%s symbol=%s errors=%s",
        PLACEMENT_REQUEST_VALIDATION_MARKER,
        ok,
        request.symbol,
        errors,
    )
    return ok, errors


@dataclass(frozen=True)
class ExecutionWiringOutcome:
    """Result of the W31I execution-wiring chokepoint.

    ``placed`` and ``executed`` are ALWAYS False in this build — no disposition reaches an order.
    """

    placed: bool
    executed: bool
    disposition: str
    reason: str
    symbol: str | None = None
    direction: str | None = None
    notional_usdt: float | None = None
    validation_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "audit_marker": EXECUTION_WIRING_AUDIT_MARKER,
            "execution_service_signature": EXECUTION_SERVICE_SIGNATURE,
            "placed": self.placed,
            "executed": self.executed,
            "disposition": self.disposition,
            "reason": self.reason,
            "symbol": self.symbol,
            "direction": self.direction,
            "notional_usdt": self.notional_usdt,
            "validation_errors": list(self.validation_errors),
        }


def prepare_execution_wiring(
    decision: AutoApprovalDecision,
    *,
    request: DemoPlacementRequest | None,
    placement_enabled: bool,
    max_notional_usdt: float,
) -> ExecutionWiringOutcome:
    """Disabled execution-wiring chokepoint. Returns a disposition only — NEVER places an order.

    Performs no I/O, imports no DB/exchange/ExecutionService symbol, and cannot build a proposal
    or call ``ExecutionService.execute``. Every return has ``placed=False`` and ``executed=False``.

    Ordering (each step short-circuits before the next, so an order is unreachable):
      1. decision not approved      -> not_approved
      2. request missing/invalid    -> placement_request_invalid
      3. placement flag is False    -> placement_flag_disabled  (the hard gate)
      4. flag True + valid request  -> execution_service_wiring_pending  (wiring intentionally unbuilt)
    """
    # 1. The policy already blocked — nothing to place.
    if not decision.approved:
        return ExecutionWiringOutcome(
            placed=False,
            executed=False,
            disposition=WIRING_NOT_APPROVED,
            reason=decision.reason,
        )

    # 2. Validate the candidate request (fails closed when fields are unavailable).
    ok, errors = validate_placement_request(request, max_notional_usdt=max_notional_usdt)
    if not ok:
        return ExecutionWiringOutcome(
            placed=False,
            executed=False,
            disposition=WIRING_REQUEST_INVALID,
            reason="; ".join(errors),
            symbol=decision.symbol,
            direction=decision.direction,
            notional_usdt=decision.notional_usdt,
            validation_errors=errors,
        )

    # 3. The independent placement flag is the hard gate. STOP.
    if not placement_enabled:
        outcome = ExecutionWiringOutcome(
            placed=False,
            executed=False,
            disposition=WIRING_PLACEMENT_DISABLED,
            reason="AUTO_APPROVAL_PLACE_ORDERS=false",
            symbol=decision.symbol,
            direction=decision.direction,
            notional_usdt=decision.notional_usdt,
        )
        logger.warning(
            "%s symbol=%s — decision AUTO_APPROVED_DEMO + valid request, but "
            "AUTO_APPROVAL_PLACE_ORDERS=false: no order. %s",
            NO_ORDER_PLACE_ORDERS_FALSE_MARKER,
            decision.symbol,
            json.dumps(outcome.as_dict(), default=str),
        )
        return outcome

    # 4. Flag True + valid request — reserved for a FUTURE owner-reviewed phase. The wiring to
    # build an APPROVED proposal and call ExecutionService.execute is intentionally NOT completed
    # in W31I, so even here NO order is placed.
    outcome = ExecutionWiringOutcome(
        placed=False,
        executed=False,
        disposition=WIRING_PENDING,
        reason=f"execution_service_wiring_not_completed_w31i; would route via {EXECUTION_SERVICE_SIGNATURE}",
        symbol=decision.symbol,
        direction=decision.direction,
        notional_usdt=decision.notional_usdt,
    )
    logger.warning(
        "%s symbol=%s — AUTO_APPROVAL_PLACE_ORDERS=true and request valid, but the "
        "decision->APPROVED-proposal->%s wiring is NOT enabled in W31I. NO order placed. %s",
        EXECUTION_SERVICE_WIRING_PENDING_MARKER,
        decision.symbol,
        EXECUTION_SERVICE_SIGNATURE,
        json.dumps(outcome.as_dict(), default=str),
    )
    return outcome
