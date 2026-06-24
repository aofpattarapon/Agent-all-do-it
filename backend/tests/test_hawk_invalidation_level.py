"""Tests for hawk invalidation_level pre-SAGE check and mode conflict resolution.

Covers:
- Valid directional HAWK outputs with invalidation_level pass the gate
- Directional HAWK output missing invalidation_level blocks before SAGE
- NEUTRAL votes do not require invalidation_level
- PAPER/demo env produces no mode conflict
- No exchange_execute path is invoked on a pre-SAGE block
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.db.models.user import User
from app.db.models.workflow import Run, RunStep, Workflow
from app.db.session import get_worker_db_context
from app.services.run_executor import RunExecutor
from app.services.trading_mode import resolve_trading_mode

# ── Unit tests for _check_hawk_invalidation_levels ─────────────────────────


def test_check_hawk_invalidation_levels_passes_all_directional_with_levels() -> None:
    gate_votes = {"hawk_trend": "BULLISH", "hawk_structure": "BEARISH", "hawk_counter": "NEUTRAL"}
    hawk_individual = {
        "hawk_trend": json.dumps({"vote": "BULLISH", "invalidation_level": 62000.0}),
        "hawk_structure": json.dumps({"vote": "BEARISH", "invalidation_level": 65500.0}),
        "hawk_counter": json.dumps({"vote": "NEUTRAL", "confidence": 40}),
    }
    ok, missing, levels = RunExecutor._check_hawk_invalidation_levels(gate_votes, hawk_individual)
    assert ok is True
    assert missing == []
    assert levels["hawk_trend"] == 62000.0
    assert levels["hawk_structure"] == 65500.0
    assert "hawk_counter" not in levels  # NEUTRAL excluded


def test_check_hawk_invalidation_levels_blocks_bullish_missing_level() -> None:
    gate_votes = {"hawk_trend": "BULLISH", "hawk_structure": "BULLISH", "hawk_counter": "NEUTRAL"}
    hawk_individual = {
        "hawk_trend": json.dumps({"vote": "BULLISH"}),  # missing invalidation_level
        "hawk_structure": json.dumps({"vote": "BULLISH", "invalidation_level": 61500.0}),
        "hawk_counter": json.dumps({"vote": "NEUTRAL"}),
    }
    ok, missing, levels = RunExecutor._check_hawk_invalidation_levels(gate_votes, hawk_individual)
    assert ok is False
    assert "hawk_trend" in missing
    assert levels["hawk_trend"] is None
    assert levels["hawk_structure"] == 61500.0


def test_check_hawk_invalidation_levels_blocks_explicit_null() -> None:
    gate_votes = {"hawk_trend": "BEARISH", "hawk_structure": "BEARISH", "hawk_counter": "NEUTRAL"}
    hawk_individual = {
        "hawk_trend": json.dumps({"vote": "BEARISH", "invalidation_level": None}),
        "hawk_structure": json.dumps({"vote": "BEARISH", "invalidation_level": 66000.0}),
        "hawk_counter": json.dumps({"vote": "NEUTRAL"}),
    }
    ok, missing, _ = RunExecutor._check_hawk_invalidation_levels(gate_votes, hawk_individual)
    assert ok is False
    assert "hawk_trend" in missing


def test_check_hawk_invalidation_levels_neutral_only_always_passes() -> None:
    gate_votes = {"hawk_trend": "NEUTRAL", "hawk_structure": "NEUTRAL", "hawk_counter": "NEUTRAL"}
    hawk_individual = {k: json.dumps({"vote": "NEUTRAL"}) for k in gate_votes}
    ok, missing, levels = RunExecutor._check_hawk_invalidation_levels(gate_votes, hawk_individual)
    assert ok is True
    assert missing == []
    assert levels == {}  # no directional votes → no levels required


# ── Mode conflict unit tests ────────────────────────────────────────────────


def test_trading_mode_conflict_for_paper_demo() -> None:
    # Phase 2B: PAPER + demo is now a hard conflict — PAPER is local-simulation only and
    # must never drive an order-capable exchange mode.
    with patch.dict(os.environ, {"TRADING_MODE": "PAPER", "EXCHANGE_MODE": "demo"}):
        status = resolve_trading_mode()
    assert status.conflict is not None
    assert "PAPER" in status.conflict
    assert status.is_local_simulation is False  # exchange_mode is demo
    assert status.is_order_capable is True


def test_trading_mode_no_conflict_for_paper_paper() -> None:
    with patch.dict(os.environ, {"TRADING_MODE": "PAPER", "EXCHANGE_MODE": "paper"}):
        status = resolve_trading_mode()
    assert status.conflict is None
    assert status.is_local_simulation is True
    assert status.is_paper is True
    assert status.is_order_capable is False


def test_trading_mode_no_conflict_for_demo_demo() -> None:
    with patch.dict(os.environ, {"TRADING_MODE": "DEMO", "EXCHANGE_MODE": "demo"}):
        status = resolve_trading_mode()
    assert status.conflict is None
    assert status.is_demo is True
    assert status.is_order_capable is True
    assert status.is_local_simulation is False
    assert status.is_paper is False  # demo is NOT local simulation
    assert status.is_live is False


def test_trading_mode_conflict_detected_for_live_plus_demo() -> None:
    with patch.dict(os.environ, {"TRADING_MODE": "LIVE", "EXCHANGE_MODE": "demo"}):
        status = resolve_trading_mode()
    assert status.conflict is not None
    assert "LIVE" in status.conflict


def test_trading_mode_conflict_detected_for_demo_plus_live() -> None:
    with patch.dict(os.environ, {"TRADING_MODE": "DEMO", "EXCHANGE_MODE": "live"}):
        status = resolve_trading_mode()
    assert status.conflict is not None


# ── Integration: pre-SAGE block on missing invalidation_level ───────────────


@pytest.fixture
async def db_session() -> AsyncSession:
    async with get_worker_db_context() as session:
        yield session


async def _seed_scope(
    db: AsyncSession,
    *,
    hawk_votes: dict[str, dict],  # step_key → full output dict
) -> tuple[User, Project, Workflow, Run]:
    user = User(
        email=f"inv-level-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="user",
        is_active=True,
        is_app_admin=False,
    )
    db.add(user)
    await db.flush()

    project = Project(user_id=user.id, name=f"InvLevel {uuid4().hex[:6]}")
    db.add(project)
    await db.flush()

    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        }
    ]
    workflow = Workflow(
        project_id=project.id,
        name=f"InvLevel Workflow {uuid4().hex[:6]}",
        trigger_kind="manual",
        definition_json={"steps": steps},
    )
    db.add(workflow)
    await db.flush()

    run = Run(
        project_id=project.id, workflow_id=workflow.id, trigger="manual", input_payload_json={}
    )
    db.add(run)
    await db.flush()

    for step_key, output_dict in hawk_votes.items():
        db.add(
            RunStep(
                run_id=run.id,
                step_key=step_key,
                step_kind="prompt",
                status="completed",
                output_json={"output": json.dumps(output_dict)},
            )
        )
    await db.flush()
    return user, project, workflow, run


async def _cleanup(
    db: AsyncSession,
    *,
    user: User,
    project: Project,
    workflow: Workflow,
    run: Run,
) -> None:
    await db.execute(delete(RunStep).where(RunStep.run_id == run.id))
    await db.execute(delete(Run).where(Run.id == run.id))
    await db.execute(delete(Workflow).where(Workflow.id == workflow.id))
    await db.execute(delete(Project).where(Project.id == project.id))
    await db.execute(delete(User).where(User.id == user.id))
    await db.flush()


@pytest.mark.anyio
async def test_hawk_gate_passes_when_directional_votes_have_invalidation_level(
    db_session: AsyncSession,
) -> None:
    """BULLISH 2/3 majority with all directional invalidation_levels → completed, no block."""
    user, project, workflow, run = await _seed_scope(
        db_session,
        hawk_votes={
            "hawk_trend": {
                "agent": "hawk_trend",
                "vote": "BULLISH",
                "confidence": 70,
                "invalidation_level": 61000.0,
            },
            "hawk_structure": {
                "agent": "hawk_structure",
                "vote": "BULLISH",
                "confidence": 65,
                "invalidation_level": 61200.0,
            },
            "hawk_counter": {"agent": "hawk_counter", "vote": "NEUTRAL", "confidence": 50},
        },
    )
    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        # Single-step workflow — gate is the only step; must complete (not be blocked on inv_level).
        assert completed.status == "completed"
        assert completed.pause_reason != "hawk_missing_invalidation_level"
    finally:
        await _cleanup(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_hawk_gate_blocks_before_sage_when_directional_vote_missing_invalidation_level(
    db_session: AsyncSession,
) -> None:
    """BULLISH 2/3 majority but hawk_trend missing invalidation_level → blocked before SAGE."""
    user, project, workflow, run = await _seed_scope(
        db_session,
        hawk_votes={
            "hawk_trend": {
                "agent": "hawk_trend",
                "vote": "BULLISH",
                "confidence": 70,
            },  # no invalidation_level
            "hawk_structure": {
                "agent": "hawk_structure",
                "vote": "BULLISH",
                "confidence": 65,
                "invalidation_level": 61200.0,
            },
            "hawk_counter": {"agent": "hawk_counter", "vote": "NEUTRAL", "confidence": 50},
        },
    )
    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "blocked"
        assert completed.pause_reason == "hawk_missing_invalidation_level"
        # Verify the block happened at hawk_vote_gate step, not sage_review.
        steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        step_keys = {s.step_key for s in steps}
        assert "hawk_vote_gate" in step_keys
        assert "sage_review" not in step_keys  # never reached
    finally:
        await _cleanup(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_hawk_gate_neutral_votes_do_not_require_invalidation_level(
    db_session: AsyncSession,
) -> None:
    """All NEUTRAL votes → gate blocked (no majority), but NOT due to missing invalidation_level."""
    user, project, workflow, run = await _seed_scope(
        db_session,
        hawk_votes={
            "hawk_trend": {"agent": "hawk_trend", "vote": "NEUTRAL", "confidence": 40},
            "hawk_structure": {"agent": "hawk_structure", "vote": "NEUTRAL", "confidence": 35},
            "hawk_counter": {
                "agent": "hawk_counter",
                "vote": "BEARISH",
                "confidence": 55,
                "invalidation_level": 65000.0,
            },
        },
    )
    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "blocked"
        # Blocked for no majority, not for missing invalidation_level.
        assert completed.pause_reason == "hawk_vote_no_majority"
    finally:
        await _cleanup(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_hawk_gate_block_does_not_invoke_exchange_execute(
    db_session: AsyncSession,
) -> None:
    """When blocked at hawk_missing_invalidation_level, no execute_trade step runs."""
    user, project, workflow, run = await _seed_scope(
        db_session,
        hawk_votes={
            "hawk_trend": {
                "agent": "hawk_trend",
                "vote": "BEARISH",
                "confidence": 70,
            },  # missing level
            "hawk_structure": {
                "agent": "hawk_structure",
                "vote": "BEARISH",
                "confidence": 65,
                "invalidation_level": 65500.0,
            },
            "hawk_counter": {"agent": "hawk_counter", "vote": "NEUTRAL", "confidence": 45},
        },
    )
    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.pause_reason == "hawk_missing_invalidation_level"
        steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        executed_keys = {s.step_key for s in steps}
        assert "execute_trade" not in executed_keys
        assert "exchange_execute" not in executed_keys
    finally:
        await _cleanup(db_session, user=user, project=project, workflow=workflow, run=run)
