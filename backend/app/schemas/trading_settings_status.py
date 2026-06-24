"""Read-only Trading Settings Sync status schema (Phase W32A).

A single source-of-truth, read-only view that consolidates trading-mode flags,
auto-approval policy, validation-only/schedule posture, W29 / W31J readiness,
order-readiness blockers and checkpoint/resume info for frontend inspection.

STRICTLY READ-ONLY: building or returning this object never places an order, never
mutates env/settings/schedules/validation_only, and never exposes secret values.
``can_send_order_now`` is fail-closed and is expected to be ``False`` while W29 is
HOLD and ``AUTO_APPROVAL_PLACE_ORDERS`` is false.
"""

from __future__ import annotations

from app.schemas.base import BaseSchema


class EffectiveModeStatus(BaseSchema):
    trading_mode: str
    exchange_mode: str
    market_type: str
    live_trading_enabled: bool
    is_paper: bool
    is_demo: bool
    is_testnet: bool
    is_live: bool
    order_destination: str


class AutoApprovalStatus(BaseSchema):
    enabled: bool
    place_orders: bool
    scope: str
    max_notional_usdt: float
    max_open_positions: int
    max_orders_per_day: int
    cooldown_minutes: int
    ready_confirmation_ticks: int
    ready_confirmation_ttl_seconds: int
    ready_confirmation_max_gap_seconds: int
    # The guarded auto-approval *evaluator* runs in the Celery worker/beat processes,
    # which hold the authoritative AUTO_APPROVAL_* environment. The API process may not
    # mirror those env vars, so callers must treat the booleans as the backend-process
    # view and rely on ``authoritative_process`` / ``note`` for provenance.
    authoritative_process: str
    note: str


class ValidationStatus(BaseSchema):
    auto_30m_validation_only: bool
    auto_15m_validation_only: bool
    note: str


class SchedulesStatus(BaseSchema):
    enabled_count: int
    total_count: int
    enabled_names: list[str]
    auto_30m_cron_enabled: bool
    auto_15m_cron_enabled: bool
    position_monitor_enabled: bool
    market_watch_enabled: bool
    screeners_enabled: bool


class ReadinessStatus(BaseSchema):
    latest_w29_posture: str | None
    latest_recommended_action: str | None
    latest_ready_symbol: str | None
    ready_confirmations: int
    required_confirmations: int
    latest_w31j_verdict: str
    order_readiness_verdict: str
    order_capable: bool
    dispatch_capable: bool
    approval_required_for_retry: bool
    validation_only_unchanged: bool
    blockers: list[str]


class ArtifactsStatus(BaseSchema):
    open_positions: int
    open_orders: int | None
    algo_orders: int | None
    proposals_count: int
    executions_count: int
    risk_ack_count: int
    proposals_today: int
    executions_today: int
    note: str


class CheckpointStatus(BaseSchema):
    latest_checkpoint_path: str | None
    latest_checkpoint_timestamp: str | None
    resume_recommendation: str


class SafetyStatus(BaseSchema):
    can_send_order_now: bool
    can_send_order_reasons: list[str]
    unsafe_flags: list[str]
    ui_lock_reasons: dict[str, str]


class TradingSettingsStatus(BaseSchema):
    """Aggregated, read-only Trading Settings Sync status object."""

    project_id: str
    generated_at: str
    effective_mode: EffectiveModeStatus
    auto_approval: AutoApprovalStatus
    validation: ValidationStatus
    schedules: SchedulesStatus
    readiness: ReadinessStatus
    artifacts: ArtifactsStatus
    checkpoint: CheckpointStatus
    safety: SafetyStatus
    mutation_supported: bool
    mutation_note: str
