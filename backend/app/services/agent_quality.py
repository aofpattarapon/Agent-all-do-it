"""Agent Quality service — read-only aggregation for Phase F dashboard.

This module aggregates existing run_steps, runs, handoffs, and agent_votes into
per-agent quality metrics. It performs no writes, no prompt changes, no model
runtime changes, and no trading decisions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.handoff import Handoff
from app.db.models.project import AgentConfig
from app.db.models.workflow import Run, RunStep
from app.services.run_status_classifier import (
    ERROR as DISPLAY_ERROR,
)
from app.services.run_status_classifier import (
    to_display_status,
)

# Pause reasons that are intentional decision blocks, NOT agent failures.
_DECISION_PAUSE_REASONS = frozenset({
    "hawk_vote_no_majority",
    "hawk_missing_invalidation_level",
    "sage_veto",
    "rejected",
})

# System / risk / concurrency limits are NOT agent failures.
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

# Handoff failures ARE agent-output quality failures.
_ERROR_PAUSE_REASONS = frozenset({
    "handoff_validation_failed",
    "handoff_contract_failed",
})

# Markers that indicate malformed JSON / schema / validation failures from an agent.
_ERROR_OUTPUT_MARKERS = frozenset({
    "invalid_short_stop_loss",
    "invalid_long_stop_loss",
    "missing required field",
    "malformed json",
    "invalid json",
    "schema validation failed",
    "required key",
})


def _is_agent_output_error(run: Run, agent_id: UUID, agent_step_ids: set[UUID]) -> bool:
    """Return True when a run's error signal can be attributed to agent output quality.

    This mirrors the frontend/backend canonical error classification:
      * handoff_validation_failed / handoff_contract_failed are quality failures.
      * invalid stop-loss markers in output/error text are validation failures.
      * HAWK no-majority, SAGE veto, human/system rejects, and limits are NOT.
    """
    pause = (run.pause_reason or "").strip()
    if pause in _ERROR_PAUSE_REASONS:
        return True

    haystack = f"{run.error_text or ''} {run.output_text or ''}".lower()
    return any(marker in haystack for marker in _ERROR_OUTPUT_MARKERS)


def _has_handoff_contract_failure(run: Run, agent_id: UUID, handoffs: list[Handoff]) -> bool:
    run_id = run.id
    for h in handoffs:
        if h.run_id != run_id:
            continue
        if h.from_agent_id != agent_id and h.to_agent_id != agent_id:
            continue
        quality = h.quality_gate_result or {}
        if quality.get("passed") is False:
            return True
    return False


class AgentQualityService:
    """Read-only aggregator for agent quality metrics."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def aggregate(self, project_id: UUID) -> dict[str, Any]:
        """Return per-agent quality metrics."""
        # 1. Agents in this project.
        agent_result = await self._db.execute(
            select(AgentConfig)
            .where(AgentConfig.project_id == project_id)
            .order_by(AgentConfig.order_index, AgentConfig.created_at)
        )
        agents: list[AgentConfig] = list(agent_result.scalars().all())

        # 2. All runs for the project.
        run_result = await self._db.execute(
            select(Run).where(Run.project_id == project_id)
        )
        runs: list[Run] = list(run_result.scalars().all())
        run_ids = [r.id for r in runs]

        # 3. All run_steps for those runs, eagerly loading run relationship.
        steps: list[RunStep] = []
        if run_ids:
            step_result = await self._db.execute(
                select(RunStep)
                .where(RunStep.run_id.in_(run_ids))
                .options(selectinload(RunStep.run))
                .order_by(RunStep.created_at)
            )
            steps = list(step_result.scalars().all())

        # 4. All handoffs for the project.
        handoff_result = await self._db.execute(
            select(Handoff).where(Handoff.project_id == project_id)
        )
        handoffs: list[Handoff] = list(handoff_result.scalars().all())

        # Group steps by agent.
        steps_by_agent: dict[UUID, list[RunStep]] = {a.id: [] for a in agents}
        run_ids_by_agent: dict[UUID, set[UUID]] = {a.id: set() for a in agents}
        for step in steps:
            if step.agent_config_id in steps_by_agent:
                steps_by_agent[step.agent_config_id].append(step)
                run_ids_by_agent[step.agent_config_id].add(step.run_id)

        # Pre-compute display status per run.
        run_display: dict[UUID, str] = {}
        for run in runs:
            # We don't have the full trade-outcome evidence here, but the canonical
            # display_status can be derived from raw fields for the signals we care about.
            display = to_display_status(None, run.status or "", run.pause_reason or "")
            run_display[run.id] = display["display_status"]

        items: list[dict[str, Any]] = []
        for agent in agents:
            agent_steps = steps_by_agent.get(agent.id, [])
            agent_run_ids = run_ids_by_agent.get(agent.id, set())

            total_steps = len(agent_steps)
            successful_outputs = sum(
                1 for s in agent_steps if (s.status or "") == "completed"
            )
            failed_outputs = sum(
                1 for s in agent_steps if (s.status or "") == "failed"
            )
            total_runs = len(agent_run_ids)

            validation_failures = 0
            contract_failures = 0
            retry_count = 0
            error_runs = 0
            last_activity: datetime | None = None

            for run in runs:
                if run.id not in agent_run_ids:
                    continue

                pause = (run.pause_reason or "").strip()
                display = run_display.get(run.id, "active")

                # Handoff failures attributed to the agent if it participated in the run.
                if pause == "handoff_validation_failed":
                    validation_failures += 1
                if pause == "handoff_contract_failed" or _has_handoff_contract_failure(
                    run, agent.id, handoffs
                ):
                    contract_failures += 1

                # Retry count from run recovery.
                retry_count += getattr(run, "recovery_count", 0) or 0

                # Error runs: genuine system/validation/agent-output errors only.
                # HAWK no-majority, SAGE veto, complete-reject, and limits are NOT errors.
                if display == DISPLAY_ERROR and _is_agent_output_error(run, agent.id, {s.id for s in agent_steps}):
                    error_runs += 1

                # Last activity across runs / steps.
                candidates = [
                    run.finished_at,
                    run.created_at,
                ]
                for ts in candidates:
                    if ts is not None and (last_activity is None or ts > last_activity):
                        last_activity = ts

            for step in agent_steps:
                if step.finished_at is not None and (
                    last_activity is None or step.finished_at > last_activity
                ):
                    last_activity = step.finished_at
                if step.created_at is not None and (
                    last_activity is None or step.created_at > last_activity
                ):
                    last_activity = step.created_at

            quality_rate = (
                round((successful_outputs / total_steps) * 100, 1)
                if total_steps > 0
                else 0.0
            )

            items.append({
                "agent_id": agent.id,
                "name": agent.name,
                "role": agent.role,
                "is_active": agent.is_active,
                "total_steps": total_steps,
                "total_runs": total_runs,
                "successful_outputs": successful_outputs,
                "failed_outputs": failed_outputs,
                "validation_failures": validation_failures,
                "contract_failures": contract_failures,
                "retry_count": retry_count,
                "error_runs": error_runs,
                "last_activity": last_activity,
                "quality_rate": quality_rate,
            })

        return {
            "items": items,
            "generated_at": datetime.now(UTC),
        }
