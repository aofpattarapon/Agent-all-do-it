"""Structured handoff contracts for workflow step boundaries.

Phase 2 hardens crypto workflow handoffs so downstream steps consume explicit,
schema-shaped outputs instead of best-effort keyword matches. Contracts are
bound to concrete upstream/downstream step keys and validate JSON field paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.json_utils import extract_json_object


@dataclass(frozen=True)
class HandoffField:
    """A required or optional JSON field within a handoff payload."""

    path: str
    allow_empty: bool = False


@dataclass(frozen=True)
class HandoffContract:
    """A contract enforced between two concrete workflow boundaries."""

    name: str
    upstream_step_keys: tuple[str, ...]
    downstream_step_keys: tuple[str, ...]
    required_fields: tuple[HandoffField, ...]
    optional_fields: tuple[HandoffField, ...] = ()
    schema_version: str = "v1"
    fail_closed: bool = True


@dataclass(frozen=True)
class HandoffCheckResult:
    """Result of validating a single upstream payload against a contract."""

    passed: bool
    contract: HandoffContract
    missing_fields: tuple[str, ...]
    parse_error: str | None = None


def _get_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
            continue
        return None
    return current


def _is_present(value: Any, *, allow_empty: bool) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return allow_empty or bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return allow_empty or len(value) > 0
    return True


def validate_handoff(upstream_output: str, contract: HandoffContract) -> HandoffCheckResult:
    """Validate an upstream JSON payload against a boundary contract."""

    payload = extract_json_object(upstream_output or "")
    if not isinstance(payload, dict):
        return HandoffCheckResult(
            passed=False,
            contract=contract,
            missing_fields=tuple(field.path for field in contract.required_fields),
            parse_error="upstream output is not a valid JSON object",
        )

    missing: list[str] = []
    for field in contract.required_fields:
        value = _get_path(payload, field.path)
        if not _is_present(value, allow_empty=field.allow_empty):
            missing.append(field.path)

    return HandoffCheckResult(
        passed=not missing,
        contract=contract,
        missing_fields=tuple(missing),
        parse_error=None,
    )


CRYPTO_HANDOFF_CONTRACTS: tuple[HandoffContract, ...] = (
    HandoffContract(
        name="news_scan_to_source_check",
        upstream_step_keys=("news_scan",),
        downstream_step_keys=("source_check",),
        required_fields=(
            HandoffField("agent"),
            HandoffField("scan_timestamp"),
            HandoffField("sources_checked"),
            HandoffField("news_items", allow_empty=True),
            HandoffField("data_fetch_errors", allow_empty=True),
        ),
    ),
    HandoffContract(
        name="source_check_to_market_regime",
        upstream_step_keys=("source_check",),
        downstream_step_keys=("market_regime",),
        required_fields=(
            HandoffField("agent"),
            HandoffField("scored_at"),
            HandoffField("items", allow_empty=True),
            HandoffField("high_reliability_count"),
            HandoffField("overall_news_quality"),
        ),
    ),
    HandoffContract(
        name="market_data_to_hawk",
        upstream_step_keys=("fetch_market_data",),
        downstream_step_keys=("hawk_trend", "hawk_structure", "hawk_counter"),
        required_fields=(
            HandoffField("symbol"),
            HandoffField("price"),
            HandoffField("fear_greed"),
            HandoffField("indicators"),
            HandoffField("errors", allow_empty=True),
        ),
    ),
    HandoffContract(
        name="hawk_to_hawk_vote_gate",
        upstream_step_keys=("hawk_trend", "hawk_structure", "hawk_counter"),
        downstream_step_keys=("hawk_vote_gate",),
        required_fields=(
            HandoffField("agent"),
            HandoffField("symbol"),
            HandoffField("analyzed_at"),
            HandoffField("sources_used"),
            HandoffField("vote"),
            HandoffField("confidence"),
            HandoffField("data_quality"),
            HandoffField("market_data_snapshot"),
        ),
        optional_fields=(
            HandoffField("invalidation_level", allow_empty=True),
        ),
    ),
    HandoffContract(
        name="hawk_vote_gate_to_sage",
        upstream_step_keys=("hawk_vote_gate",),
        downstream_step_keys=("sage_review",),
        required_fields=(
            HandoffField("agent"),
            HandoffField("evaluated_at"),
            HandoffField("source_steps"),
            HandoffField("votes"),
            HandoffField("vote_tally"),
            HandoffField("majority_direction"),
            HandoffField("gate_passed"),
            HandoffField("gate_result"),
        ),
    ),
    HandoffContract(
        name="sage_to_trade_proposal",
        upstream_step_keys=("sage_review",),
        downstream_step_keys=("compile_proposal",),
        required_fields=(
            HandoffField("sage_decision"),
            HandoffField("rules_checked"),
        ),
        optional_fields=(
            HandoffField("risk_notes", allow_empty=True),
            HandoffField("approved_direction"),
        ),
    ),
    HandoffContract(
        name="trade_proposal_to_gate_or_execute",
        upstream_step_keys=("compile_proposal",),
        downstream_step_keys=(
            "auto_winrate_gate",
            "winrate_trade_gate",
            "human_approval_gate",
            "execute_trade",
        ),
        required_fields=(
            HandoffField("approval_status"),
            HandoffField("direction"),
            HandoffField("entry_plan.primary_entry"),
            HandoffField("stop_loss"),
            HandoffField("take_profit"),
            HandoffField("risk_reward"),
            HandoffField("position_size_usdt"),
            HandoffField("market_type"),
        ),
    ),
    HandoffContract(
        name="exchange_execute_to_trade_journal",
        upstream_step_keys=("execute_trade",),
        downstream_step_keys=("journal_entry",),
        required_fields=(
            HandoffField("execution_status"),
            HandoffField("symbol"),
        ),
        optional_fields=(
            HandoffField("order_id"),
            HandoffField("position_id"),
            HandoffField("sl_order_id"),
            HandoffField("tp_order_ids", allow_empty=True),
        ),
    ),
)


def contracts_for_handoff(
    upstream_step_key: str, downstream_step_key: str | None
) -> list[HandoffContract]:
    """Return contracts matching the concrete workflow boundary."""

    if not downstream_step_key:
        return []
    return [
        contract
        for contract in CRYPTO_HANDOFF_CONTRACTS
        if upstream_step_key in contract.upstream_step_keys
        and downstream_step_key in contract.downstream_step_keys
    ]
