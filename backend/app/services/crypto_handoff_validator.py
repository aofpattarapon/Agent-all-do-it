"""Crypto pipeline handoff null-validator.

Called after every prompt step to verify required fields are present and non-null
before passing data to the next agent.  On failure the run is blocked (not just warned).

Validation is role-based: each agent role has a schema of required fields with their
expected types.  The validator returns (passed, missing_fields, auto_repaired_payload)
so the executor can attempt auto-repair on non-critical fields before deciding to block.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


_VALID_VOTES = {"BULLISH", "BEARISH", "NEUTRAL"}
_VALID_DIRECTIONS = {"LONG", "SHORT"}
_VALID_SAGE_DECISIONS = {"APPROVED", "VETOED"}
_FORBIDDEN_HAWK_TOP_LEVEL_KEYS = {
    "trend_direction",
    "analysis",
    "conclusion",
    "recommendation",
}

# Canonical mapping: HAWK majority vote → required proposal direction.
_MAJORITY_TO_DIRECTION: dict[str, str] = {"BULLISH": "LONG", "BEARISH": "SHORT"}


def _is_non_null_float(value: Any) -> bool:
    if value is None:
        return False
    try:
        return float(value) != 0 or True  # 0.0 is ok
    except (TypeError, ValueError):
        return False


def _is_positive_float(value: Any) -> bool:
    if value is None:
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _is_non_null_number(value: Any) -> bool:
    return _is_non_null_float(value)


def _is_valid_str(value: Any, choices: set[str]) -> bool:
    return isinstance(value, str) and value.upper() in choices


def _nested_get(d: dict, *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


class HandoffViolation:
    def __init__(self, field: str, reason: str, critical: bool = True) -> None:
        self.field = field
        self.reason = reason
        self.critical = critical

    def __str__(self) -> str:
        severity = "CRITICAL" if self.critical else "WARNING"
        return f"[{severity}] {self.field}: {self.reason}"


def validate_hawk_output(
    payload: dict, role: str, market_price: float | None = None
) -> list[HandoffViolation]:
    """Validate HAWK-Trend, HAWK-Structure, HAWK-Counter outputs."""
    violations: list[HandoffViolation] = []

    for field in sorted(_FORBIDDEN_HAWK_TOP_LEVEL_KEYS.intersection(payload)):
        violations.append(
            HandoffViolation(
                field,
                'forbidden top-level key; place this content inside "reasoning"',
                critical=True,
            )
        )

    vote = payload.get("vote")
    if not _is_valid_str(vote, _VALID_VOTES):
        violations.append(
            HandoffViolation("vote", f"must be one of {_VALID_VOTES}, got {vote!r}", critical=True)
        )

    inv = payload.get("invalidation_level")
    if not _is_positive_float(inv):
        vote_upper = str(vote or "").upper()
        if vote_upper == "NEUTRAL":
            violations.append(
                HandoffViolation(
                    "invalidation_level",
                    "null/missing on NEUTRAL vote — not required, skipping auto-repair",
                    critical=False,
                )
            )
        elif market_price and market_price > 0:
            fallback = round(market_price * (0.97 if vote_upper == "BULLISH" else 1.03), 2)
            payload["invalidation_level"] = fallback
            payload["_invalidation_repaired"] = True
            violations.append(
                HandoffViolation(
                    "invalidation_level",
                    f"was null/zero — auto-repaired to {fallback} (price*{'0.97' if vote_upper == 'BULLISH' else '1.03'})",
                    critical=False,
                )
            )
        else:
            violations.append(
                HandoffViolation(
                    "invalidation_level",
                    "must be a positive float, cannot auto-repair without market price",
                    critical=True,
                )
            )

    confidence = payload.get("confidence")
    if not _is_non_null_float(confidence):
        violations.append(HandoffViolation("confidence", "missing or null", critical=False))

    risk_flags = payload.get("risk_flags")
    if "risk_flags" not in payload:
        violations.append(HandoffViolation("risk_flags", "missing", critical=True))
    elif not isinstance(risk_flags, list):
        violations.append(HandoffViolation("risk_flags", "must be a list", critical=True))

    return violations


def validate_sage_output(payload: dict) -> list[HandoffViolation]:
    violations: list[HandoffViolation] = []

    decision = payload.get("sage_decision")
    if not _is_valid_str(decision, _VALID_SAGE_DECISIONS):
        violations.append(
            HandoffViolation(
                "sage_decision",
                f"must be APPROVED or VETOED, got {decision!r}",
                critical=True,
            )
        )

    if isinstance(payload.get("rules_checked"), dict):
        for rule in ("hawk_majority", "market_regime_check", "invalidation_levels_present"):
            if rule not in payload["rules_checked"]:
                violations.append(
                    HandoffViolation(f"rules_checked.{rule}", "missing", critical=False)
                )

    return violations


def check_direction_majority_alignment(
    direction: str | None,
    majority_direction: str | None,
    market_type: str | None = None,
) -> list[HandoffViolation]:
    """Deterministic majority-direction guard.

    Returns critical HandoffViolations on any mismatch. Never mutates inputs.
    Never flips or repairs direction — only blocks.
    """
    violations: list[HandoffViolation] = []

    md_upper = (majority_direction or "").strip().upper()

    if not md_upper or md_upper in ("NEUTRAL", "NO_MAJORITY"):
        violations.append(
            HandoffViolation(
                "majority_direction_unavailable",
                f"majority_direction={majority_direction!r} is missing/NEUTRAL/NO_MAJORITY — "
                "no directional trade is permitted; expected approval_status=BLOCKED",
                critical=True,
            )
        )
        return violations

    expected = _MAJORITY_TO_DIRECTION.get(md_upper)
    if expected is None:
        violations.append(
            HandoffViolation(
                "majority_direction_unavailable",
                f"majority_direction={majority_direction!r} is not a recognised vote value",
                critical=True,
            )
        )
        return violations

    # Spot markets cannot go SHORT — BEARISH majority on spot must block, not flip to LONG.
    mt_lower = (market_type or "").strip().lower()
    if expected == "SHORT" and mt_lower == "spot":
        violations.append(
            HandoffViolation(
                "spot_short_unsupported",
                "majority_direction=BEARISH requires SHORT but market_type=spot does not support "
                "shorting — expected approval_status=BLOCKED (no_trade), direction must NOT be "
                "inverted to LONG",
                critical=True,
            )
        )
        return violations

    dir_upper = (direction or "").strip().upper()
    if dir_upper != expected:
        violations.append(
            HandoffViolation(
                "direction_majority_mismatch",
                f"majority_direction={md_upper} requires direction={expected}, "
                f"but proposal has direction={dir_upper!r}",
                critical=True,
            )
        )

    return violations


# approval_status values the proposal agent must never set itself at compile time.
# The compile_proposal step produces a *candidate* for human/gate approval — it may not
# self-elevate to an approved/executed state. Approval happens only via the downstream gate
# + human-approval path.
_ELEVATED_PROPOSAL_STATUSES = {"APPROVED", "EXECUTED"}


def normalize_compile_proposal_approval_status(
    payload: dict,
) -> tuple[dict, dict[str, Any], str | None]:
    """Deterministically default/guard ``approval_status`` at the compile_proposal boundary.

    The proposal agent frequently omits ``approval_status`` even when the prompt instructs
    it (observed: qwen3 dropped the field on a complete, otherwise-valid proposal), which the
    null-validator then reads as ``None`` and hard-blocks the run. This normalizer runs BEFORE
    ``validate_trade_proposal_output`` and applies a deterministic, fail-safe default.

    Returns ``(payload, metadata, block_reason)``:

    * ``approval_status`` missing or ``None`` → set to ``"PENDING_APPROVAL"`` and record
      ``approval_status_defaulted`` / ``approval_status_default_source`` in ``metadata``.
    * ``approval_status`` == ``"APPROVED"`` or ``"EXECUTED"`` → fail closed (``block_reason``
      set); the proposal agent must never self-elevate approval at compile time.
    * any other value → returned unchanged with empty ``metadata`` and no ``block_reason``;
      the null-validator still enforces the allowed set (only PENDING_APPROVAL/APPROVED pass),
      so genuinely unexpected values continue to fail closed downstream.

    Never mutates an explicit safe value (``PENDING_APPROVAL``) and never downgrades or
    silently overwrites an elevated value — elevated values block so they cannot pass silently.
    """
    metadata: dict[str, Any] = {}
    status = payload.get("approval_status")

    if status is None:
        payload["approval_status"] = "PENDING_APPROVAL"
        metadata["approval_status_defaulted"] = True
        metadata["approval_status_default_source"] = "compile_proposal_normalizer"
        return payload, metadata, None

    if isinstance(status, str) and status.strip().upper() in _ELEVATED_PROPOSAL_STATUSES:
        metadata["approval_status_rejected_elevated"] = status.strip().upper()
        return (
            payload,
            metadata,
            f"approval_status={status!r} is not permitted from compile_proposal — the proposal "
            "agent must not self-elevate approval; expected PENDING_APPROVAL (approval happens "
            "only via the winrate gate + human-approval path)",
        )

    return payload, metadata, None


def validate_trade_proposal_output(
    payload: dict, context: dict | None = None
) -> list[HandoffViolation]:
    violations: list[HandoffViolation] = []

    approval = payload.get("approval_status")
    if approval not in ("PENDING_APPROVAL", "APPROVED"):
        violations.append(
            HandoffViolation("approval_status", f"unexpected value: {approval!r}", critical=True)
        )

    direction = payload.get("direction")
    if not _is_valid_str(direction, _VALID_DIRECTIONS):
        violations.append(
            HandoffViolation(
                "direction", f"must be LONG or SHORT, got {direction!r}", critical=True
            )
        )

    entry_plan = payload.get("entry_plan")
    if not isinstance(entry_plan, dict) or not _is_positive_float(entry_plan.get("primary_entry")):
        violations.append(
            HandoffViolation(
                "entry_plan.primary_entry", "missing or not a positive float", critical=True
            )
        )

    stop_loss = payload.get("stop_loss")
    if not _is_positive_float(stop_loss):
        violations.append(
            HandoffViolation("stop_loss", "missing or not a positive float", critical=True)
        )

    tps = payload.get("take_profit")
    if not isinstance(tps, list) or len(tps) < 1:
        violations.append(
            HandoffViolation(
                "take_profit", "must be a list with at least 1 TP level", critical=True
            )
        )

    rr = payload.get("risk_reward")
    if not _is_positive_float(rr) or float(rr) < 2.0:
        violations.append(
            HandoffViolation("risk_reward", f"must be >= 2.0, got {rr!r}", critical=True)
        )

    size = payload.get("position_size_usdt")
    if not _is_positive_float(size):
        violations.append(HandoffViolation("position_size_usdt", "missing or <= 0", critical=True))

    # Direction-aware SL/TP relationship — fail fast at the proposal boundary so a
    # wrong-direction stop loss never reaches the execution preflight. Shares the single
    # rule implementation in execution_preflight (imported lazily to avoid a heavy/cyclic
    # import at module load).
    if _is_valid_str(direction, _VALID_DIRECTIONS) and isinstance(entry_plan, dict):
        from app.services.execution_preflight import validate_directional_risk_levels

        entry = entry_plan.get("primary_entry")
        try:
            entry_value = float(entry) if entry is not None else 0.0
        except (TypeError, ValueError):
            entry_value = 0.0
        tp_values: list[float] = []
        for tp in tps if isinstance(tps, list) else []:
            try:
                tp_values.append(float(tp))
            except (TypeError, ValueError):
                continue
        sl_value: float | None
        try:
            sl_value = float(stop_loss) if stop_loss is not None else None
        except (TypeError, ValueError):
            sl_value = None
        for error in validate_directional_risk_levels(
            str(direction), entry_value, sl_value, tp_values
        ):
            reason, _, message = error.partition(": ")
            violations.append(HandoffViolation(reason, message or error, critical=True))

    # Majority-direction alignment — deterministic guard, checked after direction/SL-TP
    # so the violation reason is unambiguous (not obscured by a missing direction field).
    _ctx = context or {}
    majority_direction = _ctx.get("majority_direction")
    market_type = payload.get("market_type") or _ctx.get("market_type")
    if majority_direction is not None:
        violations.extend(
            check_direction_majority_alignment(
                direction=str(direction) if direction is not None else None,
                majority_direction=str(majority_direction),
                market_type=str(market_type) if market_type is not None else None,
            )
        )

    return violations


def validate_execution_output(payload: dict) -> list[HandoffViolation]:
    violations: list[HandoffViolation] = []

    status = payload.get("execution_status")
    if status not in ("SUCCESS", "FAILED", "BLOCKED"):
        violations.append(
            HandoffViolation("execution_status", f"unexpected value: {status!r}", critical=False)
        )

    return violations


def validate_regime_output(payload: dict) -> list[HandoffViolation]:
    violations: list[HandoffViolation] = []

    if not _is_positive_float(payload.get("btc_price_usd")):
        violations.append(HandoffViolation("btc_price_usd", "missing or null", critical=False))

    regime = payload.get("market_regime")
    valid_regimes = {"RISK_ON", "RISK_OFF", "NEUTRAL", "EXTREME_GREED", "EXTREME_FEAR"}
    if not _is_valid_str(regime, valid_regimes):
        violations.append(
            HandoffViolation("market_regime", f"unexpected value: {regime!r}", critical=False)
        )

    return violations


# Role → validator function map
_ROLE_VALIDATORS = {
    "hawk_trend": lambda p, ctx: validate_hawk_output(p, "hawk_trend", ctx.get("_market_price")),
    "hawk_structure": lambda p, ctx: validate_hawk_output(
        p, "hawk_structure", ctx.get("_market_price")
    ),
    "hawk_counter": lambda p, ctx: validate_hawk_output(
        p, "hawk_counter", ctx.get("_market_price")
    ),
    "sage": lambda p, ctx: validate_sage_output(p),
    "trade_proposal": lambda p, ctx: validate_trade_proposal_output(p, ctx),
    "execution": lambda p, ctx: validate_execution_output(p),
    "market_regime": lambda p, ctx: validate_regime_output(p),
}


def validate_step_output(
    role: str,
    payload: dict,
    context: dict | None = None,
) -> tuple[bool, list[HandoffViolation]]:
    """Validate a parsed JSON step output for the given agent role.

    Returns (all_critical_passed, violations).
    `context` may contain `_market_price` for HAWK auto-repair.
    """
    validator = _ROLE_VALIDATORS.get(role)
    if validator is None:
        return True, []

    violations = validator(payload, context or {})
    all_critical_passed = not any(v.critical for v in violations)
    return all_critical_passed, violations
