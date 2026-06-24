"""Adapter that lifts the derived trade-outcome classification into a single,
unified *display status* used by both backend API responses and the frontend.

This module is a thin, pure adapter on top of
:func:`app.services.run_trade_outcome.build_run_trade_outcome`. It does NOT
re-implement any classification rules — it only:

  * renames the internal underscore statuses to the canonical hyphenated names
    used across the UI (``complete_trade`` -> ``complete-trade`` etc.),
  * removes the ``unknown`` status from the display surface by folding it
    deterministically into ``active`` (non-terminal) or ``error`` (terminal),
  * exposes convenience flags (``is_terminal``, ``is_trade_executed``,
    ``is_error``, ``is_limit``) and a coarse ``category``.

Five display statuses, no more:

    active | complete-trade | complete-reject | error | limit

The function is pure and deterministic: same inputs always give same output.
No DB, no network, no LLM.
"""

from typing import Any

from app.services.run_trade_outcome import (
    _LIMIT_PAUSE_REASONS,
    _REJECT_PAUSE_REASONS,
)

# Raw Run.status values that mean the run has reached a terminal state.
_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "blocked", "cancelled"})

# pause_reasons that represent genuine system/agent-output failures (not rejections).
_ERROR_PAUSE_REASONS = frozenset({"handoff_validation_failed", "handoff_contract_failed"})

# Markers that may appear in a derived outcome's reason/reason_code text and which
# indicate a genuine validation error (a malformed proposal), NOT a risk limit.
# These surface via execution preflight output, where the underlying outcome may be
# classified as ``limit``; on the display surface they must read as ``error``.
_ERROR_OUTCOME_MARKERS = frozenset({"invalid_short_stop_loss", "invalid_long_stop_loss"})

# Canonical hyphenated display statuses.
ACTIVE = "active"
COMPLETE_TRADE = "complete-trade"
COMPLETE_REJECT = "complete-reject"
ERROR = "error"
LIMIT = "limit"

DISPLAY_STATUSES = frozenset({ACTIVE, COMPLETE_TRADE, COMPLETE_REJECT, ERROR, LIMIT})

# Map the internal (underscore) trade-outcome status -> canonical display status.
_OUTCOME_TO_DISPLAY = {
    "active": ACTIVE,
    "complete_trade": COMPLETE_TRADE,
    "complete_reject": COMPLETE_REJECT,
    "error": ERROR,
    "limit": LIMIT,
    # "unknown" is handled separately (folded into active/error by terminality).
}

_LABELS = {
    ACTIVE: "Active",
    COMPLETE_TRADE: "Completed: Trade",
    COMPLETE_REJECT: "Completed: Rejected",
    ERROR: "Error",
    LIMIT: "Limit",
}

_CATEGORIES = {
    ACTIVE: "in_progress",
    COMPLETE_TRADE: "trade",
    COMPLETE_REJECT: "strategy_reject",
    ERROR: "system_error",
    LIMIT: "risk_limit",
}


def _shape(
    display_status: str,
    reason: str,
    raw_status: str,
) -> dict[str, Any]:
    is_terminal = raw_status in _TERMINAL_RUN_STATUSES
    return {
        "display_status": display_status,
        "display_status_label": _LABELS[display_status],
        "display_status_reason": reason,
        "display_status_category": _CATEGORIES[display_status],
        "is_terminal": is_terminal,
        "is_trade_executed": display_status == COMPLETE_TRADE,
        "is_error": display_status == ERROR,
        "is_limit": display_status == LIMIT,
    }


def _fallback_from_raw(raw_status: str, pause_reason: str) -> str:
    """Derive a display status from the raw run fields alone.

    Used when no derived trade_outcome is available (e.g. on the create/update
    responses, which intentionally skip the extra outcome queries). Conservative
    by design: never invents a trade, never hides a real error.
    """
    rs = raw_status or ""
    pause = pause_reason or ""
    if rs == "failed":
        return ERROR
    if rs in ("queued", "running", "waiting_approval", "paused"):
        return ACTIVE
    if rs == "blocked":
        if pause in _ERROR_PAUSE_REASONS:
            return ERROR
        if pause in _LIMIT_PAUSE_REASONS:
            return LIMIT
        if pause in _REJECT_PAUSE_REASONS:
            return COMPLETE_REJECT
        # Unknown block reason: a gate stopped it deliberately -> reject, not error.
        return COMPLETE_REJECT
    if rs in ("completed", "cancelled"):
        return COMPLETE_REJECT
    # Anything unrecognised and non-terminal: treat as still active (safe default).
    return ACTIVE


def to_display_status(
    trade_outcome: dict[str, Any] | None,
    raw_status: str,
    pause_reason: str = "",
) -> dict[str, Any]:
    """Adapt a derived trade outcome (or raw status) into the unified display status.

    Args:
        trade_outcome: the dict returned by ``build_run_trade_outcome``, or None.
        raw_status: the raw ``Run.status`` value (preserved separately for debug).
        pause_reason: the raw ``Run.pause_reason`` (preserved separately for debug).

    Returns a dict with the additive top-level display fields. ``unknown`` never
    leaks out: it folds to ``error`` for terminal runs, else ``active``.

    Error pauses (``_ERROR_PAUSE_REASONS``) and error output markers
    (``_ERROR_OUTCOME_MARKERS``, e.g. an invalid stop loss) are genuine
    system/validation failures: they always surface as ``error`` regardless of how
    the underlying trade-outcome classifier bucketed them. This is applied on BOTH
    the fallback path (no outcome) and the main path (computed outcome). It never
    overrides decision rejections (``hawk_vote_no_majority``, ``sage_veto``, etc.),
    which must stay ``complete-reject``.
    """
    if trade_outcome is None:
        display = _fallback_from_raw(raw_status, pause_reason)
        return _shape(display, _LABELS[display], raw_status)

    outcome_status = trade_outcome.get("status", "unknown")
    reason = trade_outcome.get("reason") or ""

    display = _OUTCOME_TO_DISPLAY.get(outcome_status)
    if display is None:
        # outcome_status == "unknown" (or anything unexpected): fold by terminality.
        display = ERROR if raw_status in _TERMINAL_RUN_STATUSES else ACTIVE
        if not reason:
            reason = _LABELS[display]

    # Error override: a deliberate error pause or an error output marker always wins
    # over a reject/limit classification (but never over decision rejections, which
    # are not in the error sets). Trade executions are unaffected — error pauses do
    # not occur on executed runs.
    if _is_error_signal(pause_reason, trade_outcome):
        display = ERROR

    return _shape(display, reason, raw_status)


def _is_error_signal(pause_reason: str, trade_outcome: dict[str, Any]) -> bool:
    """Return True when the run represents a genuine system/validation error.

    Checks the raw ``pause_reason`` against ``_ERROR_PAUSE_REASONS`` and the derived
    outcome's ``reason_code``/``reason`` text against ``_ERROR_OUTCOME_MARKERS``.
    """
    if (pause_reason or "") in _ERROR_PAUSE_REASONS:
        return True
    haystack = f"{trade_outcome.get('reason_code') or ''} {trade_outcome.get('reason') or ''}"
    return any(marker in haystack for marker in _ERROR_OUTCOME_MARKERS)
