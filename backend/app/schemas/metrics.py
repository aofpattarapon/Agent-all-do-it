"""Read-only metric response schemas (run summary + performance summary).

These describe backend-authoritative aggregates derived from the canonical
``display_status`` taxonomy (see :mod:`app.services.run_status_classifier`) and,
for trade win-rate / PnL, from closed-position ``TradeJournal`` rows only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.base import BaseSchema


class RunSummary(BaseSchema):
    """Backend-authoritative run counts for a project, by canonical display status.

    ``by_display_status`` / ``by_workflow_category`` / ``trade_pipeline`` use the
    hyphenated canonical status keys (``complete-trade`` etc.) as dict keys. Active
    runs are excluded from ``terminal`` (and from every terminal-based rate).
    """

    total: int
    terminal: int
    active: int
    by_display_status: dict[str, int]
    by_workflow_category: dict[str, int]
    trade_pipeline: dict[str, int]
    generated_at: datetime


class PerformanceSummary(BaseSchema):
    """Clearly separated workflow-health vs. trade-outcome metrics.

    Workflow rates are computed from run ``display_status`` (terminal runs only).
    Trade win-rate and PnL come exclusively from closed ``TradeJournal`` trades and
    are never derived from run outcomes (a ``complete-reject`` is not a trade loss).
    """

    terminal_runs: int
    trade_pipeline_terminal: int
    # Workflow-health rates (percent, 0-100) - over terminal runs.
    workflow_success_rate: float
    error_rate: float
    limit_rate: float
    # Trade-pipeline rates (percent, 0-100) - over terminal trade-pipeline runs.
    trade_execution_rate: float
    strategy_reject_rate: float
    # Trade outcome metrics — from TradeJournal closed trades only.
    trade_win_rate: float
    total_trades: int
    wins: int
    losses: int
    total_pnl_usdt: float
    avg_win_usdt: float
    avg_loss_usdt: float
    profit_factor: float
    # Placeholder — agent output quality scoring is deferred to a later phase.
    agent_output_quality: dict[str, Any] | None = None
    generated_at: datetime
