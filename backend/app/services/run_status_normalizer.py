"""Workflow-aware, normalized run-status classification.

This module is the project-wide source of truth for turning raw run state
plus workflow artifacts into a clean taxonomy:

    workflow_category ∈ {trade, monitor, research, screener, unknown}
    status_group     ∈ {active, done, error}
    status_subtype   ∈ {running, queued, waiting_approval, ...}

It is pure and deterministic: same inputs always give the same output.
No DB queries, no network calls, no LLM calls.

The legacy `run_trade_outcome.py` / `run_status_classifier.py` stack is kept
unchanged for backward compatibility; this normalizer provides additive fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.workflow_category_classifier import classify_workflow_category

# ── Constants ─────────────────────────────────────────────────────────────────

WORKFLOW_CATEGORIES = frozenset({"trade", "monitor", "research", "screener", "unknown"})
STATUS_GROUPS = frozenset({"active", "done", "error"})

# Decision-block pause reasons that can appear in trade workflows.
_DECISION_PAUSE_REASONS = frozenset({
    "hawk_vote_no_majority",
    "hawk_missing_invalidation_level",
    "sage_veto",
    "rejected",
})

# Limit/system-cap pause reasons. These are *not* market-evaluation rejections.
_LIMIT_PAUSE_REASONS = frozenset({
    "kill_switch",
    "daily_loss_limit",
    "risk_budget",
    "rate_limit",
    "max_open_positions",
    "concurrency_limit",
    "cost_limit",
    "schedule_lock",
    "dispatch_cap",
})

# Error pause reasons (missing/invalid required output).
_ERROR_PAUSE_REASONS = frozenset({
    "handoff_validation_failed",
    "handoff_contract_failed",
})

# Subtypes that belong to each status group.
_ACTIVE_SUBTYPES = frozenset({"running", "queued", "pending", "waiting_approval", "processing", "unknown"})
_DONE_SUBTYPES = frozenset({
    "executed",
    "decision_blocked",
    "no_trade",
    "proposal_created",
    "research_updated",
    "no_action_needed",
    "monitor_checked",
    "position_closed",
    "protection_attention",
    "screener_dispatched",
    "screener_no_candidates",
})
_ERROR_SUBTYPES = frozenset({
    "data_loss",
    "validation_error",
    "provider_error",
    "rate_limit",
    "timeout",
    "exchange_error",
    "db_error",
    "execution_error",
    "scheduler_error",
    "unknown_error",
})


# ── Data object ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NormalizedStatus:
    """Normalized status for a single run."""

    workflow_category: str
    status_group: str
    status_subtype: str
    status_label: str
    status_reason: str
    decision_reason: str | None
    error_category: str | None
    is_active: bool
    is_done: bool
    is_error: bool
    is_trade_workflow: bool
    is_monitor_workflow: bool
    is_research_workflow: bool
    is_screener_workflow: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_category": self.workflow_category,
            "status_group": self.status_group,
            "status_subtype": self.status_subtype,
            "status_label": self.status_label,
            "status_reason": self.status_reason,
            "decision_reason": self.decision_reason,
            "error_category": self.error_category,
            "is_active": self.is_active,
            "is_done": self.is_done,
            "is_error": self.is_error,
            "is_trade_workflow": self.is_trade_workflow,
            "is_monitor_workflow": self.is_monitor_workflow,
            "is_research_workflow": self.is_research_workflow,
            "is_screener_workflow": self.is_screener_workflow,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _infer_error_subtype(run_status: str, pause_reason: str, error_text: str) -> str:
    """Map raw failure signals to a fine-grained error subtype."""
    text = (error_text or "").lower()
    pause = pause_reason or ""

    if pause in _ERROR_PAUSE_REASONS:
        return "validation_error"

    if "rate limit" in text or pause == "rate_limit":
        return "rate_limit"
    if "quota" in text or "billing" in text or pause == "quota_exceeded":
        return "provider_error"
    if "timeout" in text or "timed out" in text or "orphan" in text or pause == "timeout":
        return "timeout"
    if "database" in text or "db " in text or "sql" in text:
        return "db_error"
    if "exchange" in text or "ccxt" in text or "binance" in text:
        return "exchange_error"
    if "scheduler" in text or "dispatch" in text:
        return "scheduler_error"
    if "execution" in text and run_status == "failed":
        return "execution_error"
    if "missing" in text or "required" in text or "invalid" in text:
        return "validation_error"

    return "unknown_error"


def _label_and_reason(status_group: str, subtype: str, reason_detail: str = "") -> tuple[str, str]:
    """Return (label, reason) for a given subtype."""
    detail = reason_detail.strip()

    labels: dict[str, str] = {
        # active
        "running": "Active",
        "queued": "Queued",
        "pending": "Pending",
        "waiting_approval": "Waiting Approval",
        "processing": "Processing",
        "unknown": "Active",
        # done
        "executed": "Done: Executed",
        "decision_blocked": "Done: Blocked by Decision",
        "no_trade": "Done: No Trade",
        "proposal_created": "Done: Proposal Created",
        "research_updated": "Done: Research Updated",
        "no_action_needed": "Done: No Action Needed",
        "monitor_checked": "Done: Monitor Checked",
        "position_closed": "Done: Position Closed",
        "protection_attention": "Done: Needs Attention",
        "screener_dispatched": "Done: Screener Dispatched",
        "screener_no_candidates": "Done: No Candidates",
        # error
        "data_loss": "Error: Data Loss",
        "validation_error": "Error: Validation Error",
        "provider_error": "Error: Provider Error",
        "rate_limit": "Error: Rate Limit",
        "timeout": "Error: Timeout",
        "exchange_error": "Error: Exchange Error",
        "db_error": "Error: Database Error",
        "execution_error": "Error: Execution Error",
        "scheduler_error": "Error: Scheduler Error",
        "unknown_error": "Error: Unknown",
    }

    reasons: dict[str, str] = {
        "running": "Run is currently running.",
        "queued": "Run is queued for execution.",
        "pending": "Run is pending.",
        "waiting_approval": "Waiting for human approval.",
        "processing": "Run is processing.",
        "unknown": "Run is active.",
        "executed": "Trade executed successfully.",
        "decision_blocked": "Workflow completed but a decision gate blocked the trade.",
        "no_trade": "Workflow completed with no trade opportunity.",
        "proposal_created": "Proposal created and available for approval.",
        "research_updated": "Research workflow completed and saved a valid snapshot.",
        "no_action_needed": "Workflow completed with no action required.",
        "monitor_checked": "Monitor completed checks successfully.",
        "position_closed": "Position closed and journal finalized.",
        "protection_attention": "Monitor succeeded but a position needs attention.",
        "screener_dispatched": "Screener found candidates and dispatched trade runs.",
        "screener_no_candidates": "Screener ran successfully but found no valid symbols.",
        "data_loss": "Required output or artifact is missing.",
        "validation_error": "Invalid output or handoff validation failed.",
        "provider_error": "LLM/provider API error.",
        "rate_limit": "Rate limit hit.",
        "timeout": "Run timed out or was reaped as orphaned.",
        "exchange_error": "Exchange API or order failure.",
        "db_error": "Database read/write failure.",
        "execution_error": "Deterministic execution path failed unexpectedly.",
        "scheduler_error": "Scheduler or dispatch failure.",
        "unknown_error": "Unclassified failure.",
    }

    label = labels.get(subtype, subtype.replace("_", " ").title())
    reason = reasons.get(subtype, "")
    if detail:
        if reason:
            reason = f"{reason} {detail}"
        else:
            reason = detail
    return label, reason


# ── Active classification ─────────────────────────────────────────────────────


def _classify_active(run_status: str) -> tuple[str, str, str] | None:
    if run_status == "queued":
        return "active", "queued", ""
    if run_status == "running":
        return "active", "running", ""
    if run_status == "waiting_approval":
        return "active", "waiting_approval", ""
    if run_status == "paused":
        return "active", "processing", ""
    return None


# ── Error classification ──────────────────────────────────────────────────────


def _classify_error(
    run_status: str,
    pause_reason: str,
    error_text: str,
    execution_status: str | None,
) -> tuple[str, str, str] | None:
    """Return (group, subtype, detail) for genuine error cases, or None."""
    if run_status == "failed":
        subtype = _infer_error_subtype(run_status, pause_reason, error_text)
        return "error", subtype, error_text or ""

    if run_status == "blocked" and pause_reason in _ERROR_PAUSE_REASONS:
        detail = error_text or f"{pause_reason}."
        return "error", "validation_error", detail

    if execution_status == "FAILED":
        return "error", "exchange_error", error_text or "Exchange execution attempted but failed."

    return None


# ── Trade workflow classification ─────────────────────────────────────────────


def _classify_trade(
    run_status: str,
    pause_reason: str,
    proposal_status: str | None,
    execution_status: str | None,
    position_status: str | None,
    winrate_gate_meta: dict[str, Any] | None,
) -> tuple[str, str, str] | None:
    """Classify terminal trade workflows (done.* or error.*)."""
    wg = winrate_gate_meta or {}
    pause = pause_reason or ""

    # Executed
    if execution_status in ("SUCCESS", "EXECUTED") or position_status in ("CLOSED", "PARTIAL"):
        return "done", "executed", ""

    # Decision blocks
    if pause in _DECISION_PAUSE_REASONS:
        decision_detail = {
            "hawk_vote_no_majority": "HAWK vote gate blocked: no 2/3 directional majority.",
            "hawk_missing_invalidation_level": "HAWK vote gate blocked: missing invalidation level.",
            "sage_veto": "SAGE vetoed the trade.",
            "rejected": "Trade proposal rejected by user or system.",
        }.get(pause, pause.replace("_", " ").title())
        return "done", "decision_blocked", decision_detail

    if wg.get("auto_executed") is False:
        winrate = wg.get("winrate")
        threshold = wg.get("threshold")
        if winrate is not None and threshold is not None:
            detail = f"Winrate {winrate:.1f}% < {threshold:.1f}% threshold — trade skipped."
        else:
            detail = "Winrate below threshold — trade skipped."
        return "done", "decision_blocked", detail

    if proposal_status in ("REJECTED", "EXPIRED"):
        return "done", "decision_blocked", f"Trade proposal {proposal_status.lower()}."

    # No-trade / limit-like normal outcomes
    if wg.get("skip_reason") == "open_position":
        return "done", "no_trade", "Open position cap: symbol already held."

    if pause in _LIMIT_PAUSE_REASONS:
        return "done", "no_trade", f"Blocked by system limit: {pause.replace('_', ' ').title()}."

    # Proposal created but not executed
    if proposal_status == "PENDING_APPROVAL" and run_status == "completed":
        return "done", "proposal_created", "Proposal created and waiting for approval."

    # No proposal generated at all
    if run_status == "completed" and proposal_status is None:
        return "done", "no_trade", "No valid trade opportunity."

    # Blocked with unknown reason — treat as decision block (gate stopped it)
    if run_status == "blocked":
        return "done", "decision_blocked", f"Run blocked by workflow gate: {pause or 'unknown'}."

    return None


# ── Research workflow classification ──────────────────────────────────────────


def _classify_research(
    run_status: str,
    market_snapshot: list[dict] | None,
) -> tuple[str, str, str] | None:
    if run_status != "completed":
        return None

    if market_snapshot:
        # A non-empty, valid-looking market snapshot means research succeeded.
        # We deliberately do not require specific keys; presence of the snapshot
        # artifact is sufficient. Downstream callers can pass an empty list when
        # no snapshot was saved.
        return "done", "research_updated", "Market research completed and saved a valid snapshot."

    return "done", "no_action_needed", "Research workflow completed with no action required."


# ── Monitor workflow classification ───────────────────────────────────────────


def _classify_monitor(
    run_status: str,
    monitor_snapshot: list[dict] | None,
    position_statuses: set[str] | None,
) -> tuple[str, str, str] | None:
    if run_status != "completed":
        return None

    snapshot = monitor_snapshot or []
    statuses = position_statuses or set()

    # Attention needed takes priority.
    if any(s.get("needs_attention") for s in snapshot) or "NEEDS_ATTENTION" in statuses:
        return "done", "protection_attention", "Monitor succeeded but a position needs attention."

    # Any position closed in this run.
    if "CLOSED" in statuses:
        return "done", "position_closed", "Position closed and journal finalized."

    # Non-empty snapshot with no attention means checks ran.
    if snapshot:
        return "done", "monitor_checked", "Monitor completed checks successfully."

    return "done", "no_action_needed", "Monitor completed with no open positions."


# ── Screener workflow classification ──────────────────────────────────────────


def _classify_screener(
    run_status: str,
    screener_meta: dict[str, Any] | None,
) -> tuple[str, str, str] | None:
    if run_status != "completed":
        return None

    meta = screener_meta or {}
    dispatched = meta.get("dispatched_symbols") or []
    if dispatched:
        symbols = ", ".join(dispatched)
        return "done", "screener_dispatched", f"Dispatched {len(dispatched)} candidate(s): {symbols}."

    return "done", "screener_no_candidates", "Screener ran successfully but found no valid symbols."


# ── Public API ────────────────────────────────────────────────────────────────


def normalize_run_status(
    run: Any,
    *,
    workflow: Any | None = None,
    workflow_name: str | None = None,
    workflow_category: str | None = None,
    proposal: Any | None = None,
    execution: Any | None = None,
    position: Any | None = None,
    winrate_gate_meta: dict[str, Any] | None = None,
    market_snapshot: list[dict] | None = None,
    monitor_snapshot: list[dict] | None = None,
    position_statuses: set[str] | None = None,
    screener_meta: dict[str, Any] | None = None,
) -> NormalizedStatus:
    """Return the normalized status for a run.

    Args:
        run: A ``Run`` ORM instance or any object with ``status``,
            ``pause_reason``, and ``error_text`` attributes.
        workflow: Optional ``Workflow`` instance for category inference.
        workflow_name: Optional explicit workflow name.
        workflow_category: Optional explicit category; if provided, skips inference.
        proposal: Optional ``TradeProposal`` instance.
        execution: Optional ``TradeExecution`` instance.
        position: Optional ``Position`` instance.
        winrate_gate_meta: Optional dict from the winrate_trade_gate step meta.
        market_snapshot: Optional list of market-snapshot records (research).
        monitor_snapshot: Optional list of position-monitor snapshot entries.
        position_statuses: Optional set of relevant ``Position.status`` values.
        screener_meta: Optional dict from the coin_screener step meta.
    """
    run_status = (getattr(run, "status", None) or "").lower()
    pause_reason = getattr(run, "pause_reason", None) or ""
    error_text = getattr(run, "error_text", None) or ""

    proposal_status = None
    if proposal is not None:
        proposal_status = getattr(proposal, "status", None)

    execution_status = None
    if execution is not None:
        execution_status = getattr(execution, "execution_status", None)

    position_status = None
    if position is not None:
        position_status = getattr(position, "status", None)

    category = workflow_category
    if category not in WORKFLOW_CATEGORIES:
        category = classify_workflow_category(workflow, workflow_name)

    # ── 1. Active states ──────────────────────────────────────────────────────
    active = _classify_active(run_status)
    if active is not None:
        group, subtype, detail = active
        label, reason = _label_and_reason(group, subtype, detail)
        return _build(category, group, subtype, label, reason, None, None)

    # ── 2. Genuine errors ─────────────────────────────────────────────────────
    error = _classify_error(run_status, pause_reason, error_text, execution_status)
    if error is not None:
        group, subtype, detail = error
        label, reason = _label_and_reason(group, subtype, detail)
        return _build(category, group, subtype, label, reason, None, subtype)

    # ── 3. Workflow-specific terminal classification ──────────────────────────
    result: tuple[str, str, str] | None = None
    if category == "trade":
        result = _classify_trade(
            run_status,
            pause_reason,
            proposal_status,
            execution_status,
            position_status,
            winrate_gate_meta,
        )
    elif category == "research":
        result = _classify_research(run_status, market_snapshot)
    elif category == "monitor":
        result = _classify_monitor(run_status, monitor_snapshot, position_statuses)
    elif category == "screener":
        result = _classify_screener(run_status, screener_meta)

    if result is None:
        # Fallback: terminal but unclassified.
        if run_status in ("completed", "cancelled"):
            result = ("done", "no_action_needed", "Workflow completed with no specific outcome.")
        else:
            result = ("error", "unknown_error", f"Unclassified run state: {run_status}.")

    group, subtype, detail = result
    label, reason = _label_and_reason(group, subtype, detail)

    decision_reason = None
    if subtype == "decision_blocked":
        decision_reason = detail or "Decision gate blocked the trade."

    error_category = subtype if group == "error" else None

    return _build(category, group, subtype, label, reason, decision_reason, error_category)


def _build(
    category: str,
    group: str,
    subtype: str,
    label: str,
    reason: str,
    decision_reason: str | None,
    error_category: str | None,
) -> NormalizedStatus:
    return NormalizedStatus(
        workflow_category=category,
        status_group=group,
        status_subtype=subtype,
        status_label=label,
        status_reason=reason,
        decision_reason=decision_reason,
        error_category=error_category,
        is_active=group == "active",
        is_done=group == "done",
        is_error=group == "error",
        is_trade_workflow=category == "trade",
        is_monitor_workflow=category == "monitor",
        is_research_workflow=category == "research",
        is_screener_workflow=category == "screener",
    )
