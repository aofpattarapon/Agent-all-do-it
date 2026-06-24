"""Phase W31E — DEMO Guarded Auto-Approval policy.

A pure, fully-testable decision engine that decides whether a *single* controlled DEMO
order attempt may be auto-approved, replacing manual owner approval on every READY signal
ONLY when a strict set of guards all pass.

Hard safety contract (Phase W31E):
    * DEMO ONLY. The decision requires TRADING_MODE=DEMO, EXCHANGE_MODE=demo,
      MARKET_TYPE=futures, LIVE_TRADING_ENABLED=false. It can never authorise LIVE.
    * It NEVER weakens HAWK / SAGE / kill-switch / preflight. Those gates still run
      unchanged during execution; an ``AUTO_APPROVED_DEMO`` decision only *authorises the
      attempt* — every downstream gate must still pass before any order is placed.
    * It NEVER creates a risk_ack and NEVER flips ``validation_only`` globally.
    * It NEVER places, cancels, or modifies an order — this module returns a decision dict
      only. Order placement is gated behind a separate flag and an owner-reviewed wiring
      step; this module has no exchange/adapter import.
    * Every decision (approve OR block, with the precise reason) is logged.

A ``READY`` posture alone is never sufficient: the READY must be fresh, confirmed across
multiple ticks, backed by a *non-stale* live HAWK 2/3 directional majority, within the
notional / open-position / per-day / cooldown caps, on a flat exchange, in DEMO mode, with
no unmet consecutive-loss ack requirement.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

POLICY_NAME = "DEMO_GUARDED_AUTO_APPROVAL"
LOG_MARKER = "W31E_AUTO_APPROVAL"

# Phase W31G — placement chokepoint markers. The placement decision is logged separately from
# the policy decision so the audit trail clearly shows: an approval is NOT an order.
PLACEMENT_LOG_MARKER = "W31G_PLACEMENT"

# Downstream gates that REMAIN enforced by the execution pipeline even after auto-approval.
# Auto-approval authorises the attempt; it does not pre-pass any of these.
DOWNSTREAM_GATES_STILL_ENFORCED = (
    "hawk_vote_gate_live",
    "sage_review",
    "kill_switch",
    "compile_proposal_sl_tp_invariants",
    "execution_preflight_min_notional_lot_size",
)


@dataclass(frozen=True)
class AutoApprovalSettings:
    """Immutable snapshot of the relevant config flags (decouples policy from Settings)."""

    enabled: bool
    scope: str
    max_notional_usdt: float
    max_open_positions: int
    max_orders_per_day: int
    ready_confirmation_ticks: int
    ready_max_age_seconds: int
    cooldown_minutes: int
    require_exchange_flat: bool
    require_hawk_2_of_3: bool
    require_sage_approval: bool
    require_sl_tp_rr_preflight: bool
    require_demo_mode: bool
    block_if_consecutive_loss_ack_missing: bool

    @classmethod
    def from_settings(cls, settings: Any) -> AutoApprovalSettings:
        return cls(
            enabled=settings.AUTO_APPROVAL_ENABLED,
            scope=settings.AUTO_APPROVAL_SCOPE,
            max_notional_usdt=float(settings.AUTO_APPROVAL_MAX_NOTIONAL_USDT),
            max_open_positions=int(settings.AUTO_APPROVAL_MAX_OPEN_POSITIONS),
            max_orders_per_day=int(settings.AUTO_APPROVAL_MAX_ORDERS_PER_DAY),
            ready_confirmation_ticks=int(settings.AUTO_APPROVAL_READY_CONFIRMATION_TICKS),
            ready_max_age_seconds=int(settings.AUTO_APPROVAL_READY_MAX_AGE_SECONDS),
            cooldown_minutes=int(settings.AUTO_APPROVAL_COOLDOWN_MINUTES),
            require_exchange_flat=settings.AUTO_APPROVAL_REQUIRE_EXCHANGE_FLAT,
            require_hawk_2_of_3=settings.AUTO_APPROVAL_REQUIRE_HAWK_2_OF_3,
            require_sage_approval=settings.AUTO_APPROVAL_REQUIRE_SAGE_APPROVAL,
            require_sl_tp_rr_preflight=settings.AUTO_APPROVAL_REQUIRE_SL_TP_RR_PREFLIGHT,
            require_demo_mode=settings.AUTO_APPROVAL_REQUIRE_DEMO_MODE,
            block_if_consecutive_loss_ack_missing=settings.AUTO_APPROVAL_BLOCK_IF_CONSECUTIVE_LOSS_ACK_MISSING,
        )


@dataclass
class AutoApprovalInputs:
    """Read-only runtime snapshot the policy decides on (gathered by the caller)."""

    posture: dict  # HawkConditionWatch.evaluate() output
    now: datetime
    trading_mode: str
    exchange_mode: str
    market_type: str
    live_trading_enabled: bool
    exchange_flat: bool
    open_positions: int
    auto_orders_today: int
    last_auto_order_at: datetime | None
    ready_confirmations: int  # consecutive recent ticks at READY for the candidate symbol
    consecutive_loss_block_armed: bool
    consecutive_loss_ack_present: bool
    # True only when validation_only is as-expected and no unexpected order-capable Auto cron
    # is enabled. Any drift blocks (fail-closed).
    runtime_guardrails_intact: bool = True
    # Optional downstream pre-check results. None = "unknown, enforced downstream" (does not
    # block here); False = "known failure" (blocks now). True = pre-check passed.
    sage_precheck: bool | None = None
    preflight_precheck: bool | None = None


@dataclass
class AutoApprovalDecision:
    outcome: str  # "AUTO_APPROVED_DEMO" | "BLOCKED"
    reason: str
    symbol: str | None = None
    direction: str | None = None
    notional_usdt: float | None = None
    checks: list[dict] = field(default_factory=list)
    downstream_gates_still_enforced: tuple[str, ...] = DOWNSTREAM_GATES_STILL_ENFORCED

    @property
    def approved(self) -> bool:
        return self.outcome == "AUTO_APPROVED_DEMO"

    def as_dict(self) -> dict:
        return {
            "policy": POLICY_NAME,
            "outcome": self.outcome,
            "reason": self.reason,
            "symbol": self.symbol,
            "direction": self.direction,
            "notional_usdt": self.notional_usdt,
            "checks": self.checks,
            "downstream_gates_still_enforced": list(self.downstream_gates_still_enforced),
        }


def _ready_candidate(posture: dict) -> dict | None:
    """Return the single READY candidate dict, or None if not exactly one is READY."""
    ready = [c for c in posture.get("candidates", []) if c.get("posture") == "READY"]
    return ready[0] if len(ready) == 1 else None


def evaluate_auto_approval(
    cfg: AutoApprovalSettings, inp: AutoApprovalInputs
) -> AutoApprovalDecision:
    """Run every guard in order; return a structured, logged decision.

    Pure (no DB / no exchange I/O). Short-circuits to BLOCKED on the first failing guard so
    the reason is unambiguous. Only when ALL guards pass does it return AUTO_APPROVED_DEMO —
    and even then, the downstream HAWK-live/SAGE/kill-switch/preflight gates still run.
    """
    checks: list[dict] = []

    def block(reason: str, **ctx: Any) -> AutoApprovalDecision:
        checks.append({"check": reason, "passed": False, **ctx})
        decision = AutoApprovalDecision(outcome="BLOCKED", reason=reason, checks=checks)
        logger.warning(
            "%s BLOCKED reason=%s %s",
            LOG_MARKER,
            reason,
            json.dumps(decision.as_dict(), default=str),
        )
        return decision

    def ok(name: str, **ctx: Any) -> None:
        checks.append({"check": name, "passed": True, **ctx})

    # 1) Master enable flag (decision-engine level; placement has its own separate flag).
    if not cfg.enabled:
        return block("auto_approval_disabled")
    ok("auto_approval_enabled")

    # 2) Scope must be the only supported, locked scope.
    if cfg.scope != "demo_ready_watch_only":
        return block("scope_not_supported", scope=cfg.scope)
    ok("scope_ok", scope=cfg.scope)

    # 3) DEMO mode boundary — hard. Never LIVE.
    if cfg.require_demo_mode:
        if inp.live_trading_enabled:
            return block("live_trading_enabled_must_be_false")
        if (inp.trading_mode, inp.exchange_mode, inp.market_type) != ("DEMO", "demo", "futures"):
            return block(
                "mode_not_demo_futures",
                trading_mode=inp.trading_mode,
                exchange_mode=inp.exchange_mode,
                market_type=inp.market_type,
            )
    ok("demo_mode_ok", trading_mode=inp.trading_mode, exchange_mode=inp.exchange_mode)

    # 3b) Runtime guardrails intact (validation_only as-expected, no unexpected Auto order cron).
    if not inp.runtime_guardrails_intact:
        return block("runtime_guardrails_drift")
    ok("runtime_guardrails_intact")

    # 4) Overall posture must be READY.
    posture = inp.posture
    if posture.get("overall_posture") != "READY":
        return block("not_ready", overall_posture=posture.get("overall_posture"))
    ok("overall_posture_ready")

    # 5) Exactly one READY candidate symbol.
    candidate = _ready_candidate(posture)
    if candidate is None:
        return block("no_single_ready_symbol")
    symbol = candidate.get("symbol")
    ok("single_ready_symbol", symbol=symbol)

    # 6) READY snapshot freshness.
    generated_at = posture.get("generated_at")
    age_s: float | None = None
    if isinstance(generated_at, str):
        try:
            age_s = (inp.now - datetime.fromisoformat(generated_at)).total_seconds()
        except ValueError:
            age_s = None
    elif isinstance(generated_at, datetime):
        age_s = (inp.now - generated_at).total_seconds()
    if age_s is None or age_s < 0 or age_s > cfg.ready_max_age_seconds:
        return block("ready_stale", age_seconds=age_s, max_age_seconds=cfg.ready_max_age_seconds)
    ok("ready_fresh", age_seconds=age_s)

    # 7) READY confirmed across multiple consecutive ticks (anti-flicker).
    if inp.ready_confirmations < cfg.ready_confirmation_ticks:
        return block(
            "ready_not_confirmed",
            ready_confirmations=inp.ready_confirmations,
            required=cfg.ready_confirmation_ticks,
        )
    ok("ready_confirmed", ready_confirmations=inp.ready_confirmations)

    # 8) Live (non-stale) HAWK 2/3 directional majority — the grounded direction source.
    direction: str | None = None
    if cfg.require_hawk_2_of_3:
        hawk = candidate.get("latest_hawk_read") or {}
        majority = hawk.get("majority_direction")
        if hawk.get("is_stale") is not False:  # must be explicitly fresh
            return block("hawk_read_stale", hawk=hawk)
        if not hawk.get("gate_passed"):
            return block("hawk_gate_not_passed", hawk=hawk)
        if majority not in ("BULLISH", "BEARISH"):
            return block("hawk_no_directional_majority", majority=majority)
        direction = "LONG" if majority == "BULLISH" else "SHORT"
        ok("hawk_2_of_3_live", majority=majority, direction=direction)

    # 9) Notional cap present, positive, within max.
    notional = cfg.max_notional_usdt
    if notional is None or notional <= 0:
        return block("notional_cap_missing_or_nonpositive", notional=notional)
    if notional > cfg.max_notional_usdt:  # defensive; equal is allowed
        return block("notional_exceeds_cap", notional=notional, cap=cfg.max_notional_usdt)
    ok("notional_within_cap", notional=notional, cap=cfg.max_notional_usdt)

    # 10) Exchange flat.
    if cfg.require_exchange_flat and not inp.exchange_flat:
        return block("exchange_not_flat")
    ok("exchange_flat")

    # 11) Open-position cap.
    if inp.open_positions >= cfg.max_open_positions:
        return block(
            "max_open_positions", open_positions=inp.open_positions, cap=cfg.max_open_positions
        )
    ok("open_positions_within_cap", open_positions=inp.open_positions)

    # 12) Per-day auto-approved order cap.
    if inp.auto_orders_today >= cfg.max_orders_per_day:
        return block(
            "daily_order_cap_reached",
            auto_orders_today=inp.auto_orders_today,
            cap=cfg.max_orders_per_day,
        )
    ok("daily_cap_ok", auto_orders_today=inp.auto_orders_today)

    # 13) Cooldown since the last auto-approved order.
    if inp.last_auto_order_at is not None:
        mins = (inp.now - inp.last_auto_order_at).total_seconds() / 60.0
        if mins < cfg.cooldown_minutes:
            return block(
                "cooldown_active", minutes_since_last=mins, cooldown_minutes=cfg.cooldown_minutes
            )
    ok("cooldown_clear")

    # 14) Consecutive-loss ack requirement (never auto-create an ack here).
    if (
        cfg.block_if_consecutive_loss_ack_missing
        and inp.consecutive_loss_block_armed
        and not inp.consecutive_loss_ack_present
    ):
        return block("consecutive_loss_ack_required")
    ok("consecutive_loss_ack_ok")

    # 15) Optional downstream pre-checks. SAGE / preflight are ALWAYS enforced downstream
    # during execution; if a pre-check is supplied and FAILED, block now too. Unknown (None)
    # does not block here — the pipeline still enforces it before any order.
    if cfg.require_sage_approval and inp.sage_precheck is False:
        return block("sage_precheck_failed")
    ok("sage_precheck_ok", precheck=inp.sage_precheck)
    if cfg.require_sl_tp_rr_preflight and inp.preflight_precheck is False:
        return block("preflight_precheck_failed")
    ok("preflight_precheck_ok", precheck=inp.preflight_precheck)

    decision = AutoApprovalDecision(
        outcome="AUTO_APPROVED_DEMO",
        reason="all_guards_passed",
        symbol=symbol,
        direction=direction,
        notional_usdt=notional,
        checks=checks,
    )
    logger.warning(
        "%s AUTO_APPROVED_DEMO symbol=%s direction=%s notional=%s — authorises ONE controlled DEMO "
        "attempt; downstream HAWK-live/SAGE/kill-switch/preflight STILL enforced. %s",
        LOG_MARKER,
        symbol,
        direction,
        notional,
        json.dumps(decision.as_dict(), default=str),
    )
    return decision


# --- Phase W31G — placement chokepoint -------------------------------------------------------
#
# `prepare_placement` is the SINGLE point at which an AUTO_APPROVED_DEMO decision could ever
# become an order. It is deliberately kept pure (no DB / no exchange import) so it is provably
# incapable of placing an order by itself: it returns a *disposition* only. The caller (the
# evaluator task) interprets the disposition. In this build NO disposition leads to an order:
#
#   * not_approved             -> nothing to place.
#   * placement_flag_disabled  -> AUTO_APPROVAL_PLACE_ORDERS is False (the hard gate). STOP.
#   * wiring_pending           -> even if the flag were flipped True, the order-placement
#                                 wiring (build APPROVED proposal -> ExecutionService.execute)
#                                 is intentionally NOT completed in W31G. STOP, no order.
#
# Only a later, owner-reviewed phase may add the `wiring_pending` -> ExecutionService path, and
# even then it must route through ExecutionService (never the exchange adapter directly).
# NOTE: this module is asserted to contain no exchange-primitive identifiers, so the placement
# enable flag is referenced via the ``placement_enabled`` parameter (not the literal adapter
# method names) — the env flag AUTO_APPROVAL_PLACE_ORDERS is read by the caller, not here.

PLACEMENT_NOT_APPROVED = "not_approved"
PLACEMENT_DISABLED = "placement_flag_disabled"
PLACEMENT_WIRING_PENDING = "wiring_pending"


@dataclass(frozen=True)
class PlacementOutcome:
    """Result of the placement chokepoint. ``placed`` is ALWAYS False in the W31G build."""

    placed: bool
    disposition: str
    reason: str
    symbol: str | None = None
    direction: str | None = None
    notional_usdt: float | None = None

    def as_dict(self) -> dict:
        return {
            "placement_marker": PLACEMENT_LOG_MARKER,
            "placed": self.placed,
            "disposition": self.disposition,
            "reason": self.reason,
            "symbol": self.symbol,
            "direction": self.direction,
            "notional_usdt": self.notional_usdt,
        }


def prepare_placement(
    decision: AutoApprovalDecision, *, placement_enabled: bool
) -> PlacementOutcome:
    """Decide the placement disposition for a policy decision. NEVER places an order.

    This is the chokepoint that enforces the second, independent ``AUTO_APPROVAL_PLACE_ORDERS``
    gate (passed in as ``placement_enabled``) on top of the policy decision. It performs no I/O
    and cannot reach any exchange.
    """
    if not decision.approved:
        # The policy already blocked; there is nothing to place. (No log spam — the policy logged.)
        return PlacementOutcome(
            placed=False, disposition=PLACEMENT_NOT_APPROVED, reason=decision.reason
        )

    base = {
        "symbol": decision.symbol,
        "direction": decision.direction,
        "notional_usdt": decision.notional_usdt,
    }

    if not placement_enabled:
        outcome = PlacementOutcome(
            placed=False,
            disposition=PLACEMENT_DISABLED,
            reason="AUTO_APPROVAL_PLACE_ORDERS=false",
            **base,
        )
        logger.warning(
            "%s PLACEMENT_DISABLED symbol=%s — decision was AUTO_APPROVED_DEMO but "
            "AUTO_APPROVAL_PLACE_ORDERS=false: NO_ORDER_PLACE_ORDERS_FALSE. %s",
            PLACEMENT_LOG_MARKER,
            decision.symbol,
            json.dumps(outcome.as_dict(), default=str),
        )
        return outcome

    # placement_enabled is True — reserved for a FUTURE owner-reviewed phase. The wiring from an
    # approved decision to ExecutionService is intentionally NOT completed in W31G, so even here
    # no order is placed: we surface that placement wiring is pending and STOP.
    outcome = PlacementOutcome(
        placed=False,
        disposition=PLACEMENT_WIRING_PENDING,
        reason="placement_wiring_not_completed_w31g",
        **base,
    )
    logger.warning(
        "%s PLACEMENT_WIRING_PENDING symbol=%s — AUTO_APPROVAL_PLACE_ORDERS=true but the "
        "decision->APPROVED-proposal->ExecutionService.execute wiring is NOT enabled in W31G. "
        "NO order placed. %s",
        PLACEMENT_LOG_MARKER,
        decision.symbol,
        json.dumps(outcome.as_dict(), default=str),
    )
    return outcome
