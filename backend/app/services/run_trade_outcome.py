"""Pure, read-only trade outcome computation — no DB, no network, no LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ── Known reason-code sets ─────────────────────────────────────────────────────

_ACTIVE_STATUSES = frozenset({"queued", "running", "waiting_approval", "paused"})

_REJECT_PAUSE_REASONS = frozenset(
    {
        "hawk_vote_no_majority",
        "hawk_missing_invalidation_level",
        "sage_veto",
        "rejected",
    }
)

_LIMIT_PAUSE_REASONS = frozenset(
    {
        "kill_switch",
        "daily_loss_limit",
        "risk_budget",
        "rate_limit",
        "max_open_positions",
        "concurrency_limit",
        "cost_limit",
        "schedule_lock",
        "dispatch_cap",
    }
)

# Markers in winrate-gate output text that identify deterministic exchange preflight blocks
_PREFLIGHT_NOTIONAL_MARKERS = frozenset({"PREFLIGHT NOTIONAL", "notional_usdt", "minNotional"})
_PREFLIGHT_QTY_MARKERS = frozenset({"LOT_SIZE", "MARKET_LOT_SIZE", "minQty"})


@dataclass(frozen=True)
class TradeEvidence:
    """Read-only snapshot of DB evidence used to derive a trade outcome."""

    run_status: str
    pause_reason: str
    error_text: str
    # Optional: None means "row not found", not "null field"
    proposal_status: str | None = None
    proposal_sage_approved: bool | None = None
    execution_status: str | None = None
    position_status: str | None = None
    # output_json["meta"] from the winrate_trade_gate step (if the step ran)
    winrate_gate_meta: dict[str, Any] | None = None
    # output_json["output"] text from the winrate_trade_gate step (for preflight block detection)
    winrate_gate_output: str | None = None


def _preflight_detail(output: str) -> str:
    """Extract the constraint text from an AUTO_EXECUTE_BLOCKED message."""
    # Format: "AUTO_EXECUTE_BLOCKED: Execution preflight failed: CATEGORY: detail"
    marker = "preflight failed: "
    idx = output.find(marker)
    if idx != -1:
        return output[idx + len(marker) :]
    marker = "AUTO_EXECUTE_BLOCKED: "
    idx = output.find(marker)
    if idx != -1:
        return output[idx + len(marker) :]
    return output


def build_run_trade_outcome(evidence: TradeEvidence) -> dict[str, Any]:
    """
    Derive a human-readable trade outcome from run evidence.

    Precedence (highest priority first):
        1. error          — actual failure (run.status=failed, exchange FAILED)
        2. active         — run in progress or position still OPEN
        3. complete_trade — execution succeeded / position record exists
        4. limit          — system/risk cap blocked it (not market evaluation)
        5. complete_reject — gate/veto/skip evaluated market and rejected
        6. unknown        — insufficient evidence

    The function is pure and deterministic: same inputs always give same output.
    No DB, no network, no LLM. Safe when related rows are missing (None).
    """
    rs = evidence.run_status or ""
    pause = evidence.pause_reason or ""
    wg = evidence.winrate_gate_meta or {}

    # ── 1. error ──────────────────────────────────────────────────────────────
    if rs == "failed":
        return _out(
            "error",
            "Error",
            evidence.error_text or "Run failed unexpectedly.",
            "run_failed",
            evidence,
        )
    if evidence.execution_status == "FAILED":
        return _out(
            "error",
            "Error",
            "Exchange execution attempted but failed.",
            "execution_failed",
            evidence,
        )

    # ── 2. active ─────────────────────────────────────────────────────────────
    if rs in _ACTIVE_STATUSES:
        if rs == "waiting_approval":
            return _out(
                "active", "Active", "Waiting for human approval.", "waiting_approval", evidence
            )
        return _out("active", "Active", f"Run is currently {rs}.", f"run_{rs}", evidence)
    if evidence.position_status == "OPEN":
        return _out(
            "active", "Active", "Position is open — trade still active.", "position_open", evidence
        )

    # ── 3. complete_trade ─────────────────────────────────────────────────────
    if evidence.execution_status in ("SUCCESS", "EXECUTED"):
        pos_note = " Position closed." if evidence.position_status == "CLOSED" else ""
        return _out(
            "complete_trade",
            "Complete — Trade",
            f"Trade executed successfully.{pos_note}",
            "execution_success",
            evidence,
        )
    if evidence.position_status in ("CLOSED", "PARTIAL"):
        return _out(
            "complete_trade",
            "Complete — Trade",
            "Trade position record exists for this run.",
            "position_exists",
            evidence,
        )

    # ── 4. limit ──────────────────────────────────────────────────────────────
    # Deterministic exchange/preflight block: auto_executed=True means the gate
    # attempted execution but the output text shows it was blocked by a sizing or
    # risk constraint, not a market/gate evaluation. Classify before proposal_rejected.
    wg_output_text = evidence.winrate_gate_output or ""
    if wg.get("auto_executed") is True and "AUTO_EXECUTE_BLOCKED" in wg_output_text:
        detail = _preflight_detail(wg_output_text)
        if any(m in wg_output_text for m in _PREFLIGHT_NOTIONAL_MARKERS):
            return _out(
                "limit",
                "Limit",
                f"Execution blocked by exchange minimum notional: {detail}.",
                "exchange_min_notional",
                evidence,
            )
        if any(m in wg_output_text for m in _PREFLIGHT_QTY_MARKERS):
            return _out(
                "limit",
                "Limit",
                f"Execution blocked by exchange minimum quantity: {detail}.",
                "exchange_min_quantity",
                evidence,
            )
        return _out(
            "limit",
            "Limit",
            f"Execution blocked by preflight constraint: {detail}.",
            "execution_preflight_limit",
            evidence,
        )
    if pause in _LIMIT_PAUSE_REASONS:
        label = pause.replace("_", " ").title()
        return _out("limit", "Limit", f"Blocked by system limit: {label}.", pause, evidence)
    # Open-position cap from winrate gate (symbol already held — risk/system limit)
    if wg.get("skip_reason") == "open_position":
        return _out(
            "limit",
            "Limit",
            "Open position cap: symbol already held.",
            "open_position_cap",
            evidence,
        )

    # ── 5. complete_reject ────────────────────────────────────────────────────
    if pause in _REJECT_PAUSE_REASONS:
        _msgs = {
            "hawk_vote_no_majority": "HAWK vote gate blocked: no 2/3 directional majority.",
            "hawk_missing_invalidation_level": "HAWK vote gate blocked: missing invalidation level.",
            "sage_veto": "SAGE vetoed the trade.",
            "rejected": "Trade proposal rejected.",
        }
        return _out(
            "complete_reject",
            "Complete — Rejected",
            _msgs.get(pause, f"Rejected by gate: {pause}."),
            pause,
            evidence,
        )
    # Winrate gate: auto_executed=False means below threshold and skip action taken
    if wg.get("auto_executed") is False:
        wr = wg.get("winrate")
        thr = wg.get("threshold")
        if wr is not None and thr is not None:
            reason = f"Winrate {wr:.1f}% < {thr:.1f}% threshold — trade skipped."
        else:
            reason = "Winrate below threshold — trade skipped."
        return _out(
            "complete_reject", "Complete — Rejected", reason, "winrate_below_threshold", evidence
        )
    # Proposal explicitly rejected or expired
    if evidence.proposal_status in ("REJECTED", "EXPIRED"):
        ps = (evidence.proposal_status or "").lower()
        return _out(
            "complete_reject",
            "Complete — Rejected",
            f"Trade proposal {ps}.",
            f"proposal_{ps}",
            evidence,
        )
    # Proposal still PENDING with no execution after run completed
    if evidence.proposal_status == "PENDING_APPROVAL" and rs == "completed":
        return _out(
            "complete_reject",
            "Complete — Rejected",
            "Proposal not approved — auto-gate did not execute.",
            "proposal_pending_no_execution",
            evidence,
        )
    # Run completed with no proposal generated at all
    if rs == "completed" and evidence.proposal_status is None:
        return _out(
            "complete_reject",
            "Complete — Rejected",
            "Run completed with no trade proposal generated.",
            "no_proposal",
            evidence,
        )
    # Run blocked but pause_reason not in a known set
    if rs == "blocked":
        return _out(
            "complete_reject",
            "Complete — Rejected",
            f"Run blocked by workflow gate: {pause or 'unknown'}.",
            pause or "gate_blocked",
            evidence,
        )

    # ── 6. unknown ────────────────────────────────────────────────────────────
    return _out(
        "unknown",
        "Unknown",
        "Insufficient evidence to determine trade outcome.",
        "unknown",
        evidence,
    )


def _out(
    outcome_status: str,
    label: str,
    reason: str,
    reason_code: str,
    evidence: TradeEvidence,
) -> dict[str, Any]:
    wg = evidence.winrate_gate_meta or {}
    return {
        "status": outcome_status,
        "label": label,
        "reason": reason,
        "reason_code": reason_code,
        "evidence": {
            "run_status": evidence.run_status,
            "pause_reason": evidence.pause_reason or None,
            "has_execution": evidence.execution_status is not None,
            "has_position": evidence.position_status is not None,
            "has_open_position": evidence.position_status == "OPEN",
            "proposal_status": evidence.proposal_status,
            "execution_status": evidence.execution_status,
            "position_status": evidence.position_status,
            "winrate_auto_executed": wg.get("auto_executed"),
            "winrate_skip_reason": wg.get("skip_reason"),
        },
    }
