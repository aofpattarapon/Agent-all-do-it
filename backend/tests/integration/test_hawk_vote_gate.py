"""Integration tests for the code-level HAWK majority gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.crypto_trading import (
    Position,
    TradeExecution,
    TradeJournal,
    TradeProposal,
)
from app.db.models.project import Project
from app.db.models.user import User
from app.db.models.workflow import Run, RunStep, Workflow
from app.db.session import get_worker_db_context
from app.services.run_executor import RunExecutor


@pytest.fixture
async def db_session() -> AsyncSession:
    async with get_worker_db_context() as session:
        yield session


async def _seed_scope(
    db: AsyncSession,
    *,
    steps: list[dict],
    hawk_votes: dict[str, str],
    definition_extra: dict | None = None,
    input_payload: dict | None = None,
) -> tuple[User, Project, Workflow, Run]:
    user = User(
        email=f"hawk-vote-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="user",
        is_active=True,
        is_app_admin=False,
    )
    db.add(user)
    await db.flush()

    project = Project(user_id=user.id, name=f"Hawk Vote {uuid4().hex[:6]}")
    db.add(project)
    await db.flush()

    definition_json = {"steps": steps}
    if definition_extra:
        definition_json.update(definition_extra)

    workflow = Workflow(
        project_id=project.id,
        name=f"Hawk Vote Workflow {uuid4().hex[:6]}",
        trigger_kind="manual",
        definition_json=definition_json,
    )
    db.add(workflow)
    await db.flush()

    run = Run(
        project_id=project.id,
        workflow_id=workflow.id,
        trigger="manual",
        input_payload_json=input_payload or {},
    )
    db.add(run)
    await db.flush()

    for step_key, vote in hawk_votes.items():
        db.add(
            RunStep(
                run_id=run.id,
                step_key=step_key,
                step_kind="prompt",
                status="completed",
                output_json={
                    "output": json.dumps(
                        {
                            "agent": step_key,
                            "vote": vote,
                            "confidence": 75,
                            "invalidation_level": 65000.0,
                        }
                    )
                },
            )
        )
    await db.flush()
    return user, project, workflow, run


async def _cleanup_scope(
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
async def test_hawk_vote_gate_blocks_run_without_directional_majority(
    db_session: AsyncSession,
) -> None:
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        },
        {
            "key": "sage_review",
            "kind": "prompt",
            "agent_key": str(uuid4()),
            "config": {"prompt": "Return JSON only."},
        },
    ]
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BEARISH",
            "hawk_counter": "NEUTRAL",
        },
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "blocked"
        # pause_reason is hawk_vote_no_majority (not hawk_invalid_market_data)
        assert completed.pause_reason == "hawk_vote_no_majority"
        assert "no 2/3 directional majority" in completed.error_text

        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        assert any(step.step_key == "hawk_vote_gate" for step in run_steps)
        assert not any(step.step_key == "sage_review" for step in run_steps)

        gate_step = next(step for step in run_steps if step.step_key == "hawk_vote_gate")
        gate_output = json.loads(gate_step.output_json["output"])
        assert gate_output["gate_result"] == "BLOCKED"
        # 1-1-1 three-way tie → no plurality → NO_MAJORITY
        assert gate_output["majority_direction"] == "NO_MAJORITY"
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_hawk_vote_gate_allows_run_with_two_of_three_majority(
    db_session: AsyncSession,
) -> None:
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        }
    ]
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "completed"
        assert completed.output_text
        payload = json.loads(completed.output_text)
        assert payload["gate_result"] == "PASSED"
        assert payload["majority_direction"] == "BULLISH"
        assert payload["majority_count"] == 2
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_validation_only_stops_after_hawk_vote_gate_without_execution(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        },
        {"key": "sage_review", "kind": "prompt", "agent_key": str(uuid4())},
        {
            "key": "auto_winrate_gate",
            "kind": "winrate_trade_gate",
            "config": {"warmup_trades": 10, "skip_steps_on_auto": 1},
        },
        {"key": "execute_trade", "kind": "exchange_execute"},
    ]
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": True},
        input_payload={"symbol": "BTCUSDT"},
    )

    async def fail_if_called(*_args, **_kwargs) -> str:
        raise AssertionError("validation_only run reached auto execution")

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", fail_if_called)

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "completed"
        output = json.loads(completed.output_text)
        assert output["validation_only"] is True
        assert output["stopped_after"] == "hawk_vote_gate"
        assert output["stopped_before"] == "sage_review"
        assert output["no_order_placed"] is True

        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        step_keys = {step.step_key for step in run_steps}
        assert "hawk_vote_gate" in step_keys
        assert "sage_review" not in step_keys
        assert "auto_winrate_gate" not in step_keys
        assert "execute_trade" not in step_keys

        executions = (
            (
                await db_session.execute(
                    select(TradeExecution).where(TradeExecution.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        positions = (
            (await db_session.execute(select(Position).where(Position.project_id == project.id)))
            .scalars()
            .all()
        )
        assert executions == []
        assert positions == []
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_validation_only_false_preserves_auto_gate_path(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Warmup auto-execute still works when explicitly opted in via warmup_mode=auto_execute.

    W22E made the warmup default ``pending_approval``; this test sets the node config
    ``warmup_mode=auto_execute`` to preserve the legacy auto-gate path.
    """
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        },
        {
            "key": "auto_winrate_gate",
            "kind": "winrate_trade_gate",
            "config": {
                "warmup_trades": 10,
                "skip_steps_on_auto": 1,
                "warmup_mode": "auto_execute",
            },
        },
        {"key": "execute_trade", "kind": "exchange_execute"},
    ]
    calls: list[tuple[object, object]] = []

    async def capture_auto_execute(self: RunExecutor, project_id, run_id) -> str:
        calls.append((project_id, run_id))
        return "AUTO_EXECUTED_TEST"

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", capture_auto_execute)
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": False},
        input_payload={"symbol": "BTCUSDT"},
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "completed"
        assert calls == [(project.id, run.id)]
        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        assert any(step.step_key == "auto_winrate_gate" for step in run_steps)
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


# ── W22E: project-configurable warmup_mode (executor-level) ──────────────────


async def _execs_and_positions(
    db: AsyncSession, project_id: object
) -> tuple[list[object], list[object]]:
    executions = (
        (await db.execute(select(TradeExecution).where(TradeExecution.project_id == project_id)))
        .scalars()
        .all()
    )
    positions = (
        (await db.execute(select(Position).where(Position.project_id == project_id)))
        .scalars()
        .all()
    )
    return list(executions), list(positions)


@pytest.mark.anyio
async def test_warmup_default_pending_approval_pauses_without_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No warmup_mode set + env default pending_approval → pause, no auto-execute, no order rows."""
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        },
        {
            "key": "auto_winrate_gate",
            "kind": "winrate_trade_gate",
            "config": {"warmup_trades": 10, "skip_steps_on_auto": 1},
        },
        {"key": "execute_trade", "kind": "exchange_execute"},
    ]

    async def fail_if_called(*_args, **_kwargs) -> str:
        raise AssertionError("pending_approval warmup must not auto-execute")

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", fail_if_called)
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": False},
        input_payload={"symbol": "BTCUSDT"},
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "waiting_approval"
        assert completed.pause_reason == "warmup_pending_approval"
        executions, positions = await _execs_and_positions(db_session, project.id)
        assert executions == []
        assert positions == []
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_warmup_default_pending_approval_gate_step_evidence(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W24A deterministic reach-the-gate proof.

    Seeds a 2/3 HAWK majority so the run deterministically passes hawk_vote and reaches
    ``auto_winrate_gate`` (no live LLM/market). With no node-level ``warmup_mode`` and a
    fresh project (closed_count < warmup_trades), the env default ``pending_approval`` must
    govern: the gate STEP itself records ``waiting_approval`` + the ``WARMUP_PENDING_APPROVAL``
    output + the full warmup meta (warmup_mode, auto_executed, trigger, closed_count,
    warmup_trades, winrate, threshold) — with no auto-execute call and no execution/position
    rows. Extends ``test_warmup_default_pending_approval_pauses_without_order`` with the
    step-level evidence assertions.
    """
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        },
        {
            "key": "auto_winrate_gate",
            "kind": "winrate_trade_gate",
            "config": {
                "warmup_trades": 10,
                "winrate_threshold": 60.0,
                "skip_steps_on_auto": 1,
            },
        },
        {"key": "execute_trade", "kind": "exchange_execute"},
    ]

    async def fail_if_called(*_args, **_kwargs) -> str:
        raise AssertionError("default pending_approval warmup must not auto-execute")

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", fail_if_called)
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": False},
        input_payload={"symbol": "BTCUSDT"},
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        # Run-level: deterministically reached the gate and paused for approval.
        assert completed.status == "waiting_approval"
        assert completed.pause_reason == "warmup_pending_approval"

        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        # The auto_winrate_gate step itself records the warmup pending-approval evidence.
        gate = next(s for s in run_steps if s.step_key == "auto_winrate_gate")
        assert gate.status == "waiting_approval"
        assert "WARMUP_PENDING_APPROVAL" in gate.output_json["output"]
        meta = gate.output_json["meta"]
        assert meta["warmup_mode"] == "pending_approval"
        assert meta["auto_executed"] is False
        assert meta["trigger"] == "warmup"
        # closed_count < warmup_trades is exactly what placed the gate in warmup.
        assert meta["closed_count"] < meta["warmup_trades"]
        assert meta["warmup_trades"] == 10
        assert "winrate" in meta
        assert meta["threshold"] == 60.0
        # The execute step was never reached — the gate returned before it.
        assert not any(s.step_key == "execute_trade" for s in run_steps)

        executions, positions = await _execs_and_positions(db_session, project.id)
        assert executions == []
        assert positions == []
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_warmup_pending_approval_resume_advances_without_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W24B deterministic approval/resume proof.

    Drives a seeded run to the warmup ``pending_approval`` pause (the W24A precondition), then
    exercises the real ``RunExecutor.resume_approved`` path. On approval the gate step is marked
    completed and the run advances to the ``exchange_execute`` step. Because the warmup pause
    created no APPROVED proposal, ``_run_exchange_execute`` skips with ``EXCHANGE_EXECUTE_SKIPPED``
    and never calls ``place_order`` (monkeypatched to raise). Proves the approval/resume path
    advances correctly while the no-APPROVED-proposal backstop prevents any exchange order:
    no ``place_order`` call, no execution row, no position row, no proposal row.
    """
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        },
        {
            "key": "auto_winrate_gate",
            "kind": "winrate_trade_gate",
            "config": {
                "warmup_trades": 10,
                "winrate_threshold": 60.0,
                "skip_steps_on_auto": 1,
            },
        },
        {"key": "execute_trade", "kind": "exchange_execute"},
    ]

    async def fail_auto_execute(*_args, **_kwargs) -> str:
        raise AssertionError("warmup resume must not auto-execute")

    async def fail_place_order(*_args, **_kwargs) -> dict:
        raise AssertionError("resume of a warmup-pending run must not place an exchange order")

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", fail_auto_execute)
    monkeypatch.setattr("app.agents.tools.exchange_tool.place_order", fail_place_order)

    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": False},
        input_payload={"symbol": "BTCUSDT"},
    )

    try:
        # 1) Reach the warmup pending-approval pause (W24A precondition).
        paused = await RunExecutor(db_session).execute(run.id, project.id)
        assert paused.status == "waiting_approval"
        assert paused.pause_reason == "warmup_pending_approval"
        # Paused on the gate step itself.
        assert paused.current_step_index == 1

        # 2) Exercise the real approval/resume path.
        resumed = await RunExecutor(db_session).resume_approved(run.id, project.id)

        # 3) Resume advanced past the gate to the (final) execute step and finished cleanly.
        assert resumed.status == "completed"
        assert resumed.pause_reason == ""
        assert resumed.paused_at is None
        assert resumed.current_step_index == len(steps)

        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        # Approval advanced past the gate (now completed).
        gate = next(s for s in run_steps if s.step_key == "auto_winrate_gate")
        assert gate.status == "completed"
        # The exchange_execute step ran and SKIPPED via the no-APPROVED-proposal backstop.
        execute_step = next(s for s in run_steps if s.step_key == "execute_trade")
        assert execute_step.status == "completed"
        assert "EXCHANGE_EXECUTE_SKIPPED" in execute_step.output_json["output"]

        # 4) No exchange order, no execution row, no position row, no proposal row.
        executions, positions = await _execs_and_positions(db_session, project.id)
        assert executions == []
        assert positions == []
        proposals = (
            (
                await db_session.execute(
                    select(TradeProposal).where(TradeProposal.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        assert proposals == []
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


_W24C_STEPS = [
    {
        "key": "hawk_vote_gate",
        "kind": "hawk_vote",
        "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
    },
    {
        "key": "auto_winrate_gate",
        "kind": "winrate_trade_gate",
        "config": {"warmup_trades": 10, "winrate_threshold": 60.0, "skip_steps_on_auto": 1},
    },
    {"key": "execute_trade", "kind": "exchange_execute"},
]


@pytest.mark.anyio
async def test_warmup_pending_approval_reject_cancels_without_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W24C Objective A — deterministic reject-path proof.

    Drives a seeded run to the warmup ``pending_approval`` pause (the W24A precondition), then
    exercises the real ``RunExecutor.resume_rejected`` path. Rejection must mark the run
    ``cancelled`` with ``pause_reason='rejected'`` and finish it WITHOUT re-entering ``execute()``
    — so the workflow never advances to ``exchange_execute``, the execute step is never created,
    and no order/execution/position/proposal row is ever written. ``place_order`` is monkeypatched
    to raise to prove the exchange is never touched on the reject path.
    """

    async def fail_auto_execute(*_args, **_kwargs) -> str:
        raise AssertionError("warmup reject must not auto-execute")

    async def fail_place_order(*_args, **_kwargs) -> dict:
        raise AssertionError("reject of a warmup-pending run must not place an exchange order")

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", fail_auto_execute)
    monkeypatch.setattr("app.agents.tools.exchange_tool.place_order", fail_place_order)

    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=_W24C_STEPS,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": False},
        input_payload={"symbol": "BTCUSDT"},
    )

    try:
        # 1) Reach the warmup pending-approval pause (W24A precondition).
        paused = await RunExecutor(db_session).execute(run.id, project.id)
        assert paused.status == "waiting_approval"
        assert paused.pause_reason == "warmup_pending_approval"
        assert paused.current_step_index == 1

        # 2) Exercise the real reject path.
        rejected = await RunExecutor(db_session).resume_rejected(run.id, project.id)

        # 3) Run is cancelled and finished; it did NOT advance to execute_trade.
        assert rejected.status == "cancelled"
        assert rejected.pause_reason == "rejected"
        assert rejected.finished_at is not None
        # Reject does not advance the step pointer past the gate.
        assert rejected.current_step_index == 1

        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        # The gate step the run paused on is marked cancelled (rejected), not completed.
        gate = next(s for s in run_steps if s.step_key == "auto_winrate_gate")
        assert gate.status == "cancelled"
        # The execute step was never created — the workflow never resumed.
        assert not any(s.step_key == "execute_trade" for s in run_steps)

        # 4) No exchange order, no execution row, no position row, no proposal row.
        executions, positions = await _execs_and_positions(db_session, project.id)
        assert executions == []
        assert positions == []
        proposals = (
            (
                await db_session.execute(
                    select(TradeProposal).where(TradeProposal.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )
        assert proposals == []
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


async def _seed_consecutive_loss_history(
    db: AsyncSession, project_id: object, symbol: str = "BTCUSDT"
) -> None:
    """Seed a closed losing-trade chain so the consecutive-loss kill-switch will block.

    The kill-switch reads the last ``KILL_SWITCH_CONSECUTIVE_LOSS_BLOCK`` (default 3)
    ``TradeJournal.result`` rows for the project; if all are ``LOSS`` and no active risk_ack
    exists, it blocks. ``TradeJournal.position_id`` is a non-null FK, so a minimal
    proposal→execution→position chain is created first to anchor the journal rows. All rows
    are under the throwaway project and are removed by the project-cascade in ``_cleanup_scope``.
    """
    hist_proposal = TradeProposal(
        project_id=project_id,
        run_id=uuid4(),
        symbol=symbol,
        direction="LONG",
        entry_plan={"entry": 50000.0},
        take_profit=[{"price": 51000.0}],
        stop_loss=49000.0,
        position_size_usdt=100.0,
        status="EXECUTED",
    )
    db.add(hist_proposal)
    await db.flush()

    hist_execution = TradeExecution(
        project_id=project_id,
        proposal_id=hist_proposal.id,
        exchange="test_seed",
        symbol=symbol,
        side="LONG",
        execution_status="SUCCESS",
    )
    db.add(hist_execution)
    await db.flush()

    hist_position = Position(
        project_id=project_id,
        execution_id=hist_execution.id,
        symbol=symbol,
        side="LONG",
        entry_price=50000.0,
        size=0.002,
        status="CLOSED",
    )
    db.add(hist_position)
    await db.flush()

    for _ in range(3):
        db.add(
            TradeJournal(
                project_id=project_id,
                position_id=hist_position.id,
                symbol=symbol,
                direction="LONG",
                entry_price=50000.0,
                size=0.002,
                result="LOSS",
                realized_pnl=-1.0,
            )
        )
    await db.flush()


@pytest.mark.anyio
async def test_resume_with_approved_proposal_blocked_by_kill_switch_no_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W24C Objective B — approved-proposal resume backstop proof (kill-switch).

    The one path where resume could actually reach ``place_order`` is when an APPROVED proposal
    *exists* for the run. This test deliberately seeds — TEST-ONLY, never production behavior —
    a fully-valid APPROVED ``TradeProposal`` for the resumed run, plus a closed 3x LOSS history so
    the consecutive-loss kill-switch is armed. On ``resume_approved`` the run advances to
    ``exchange_execute``, which finds the APPROVED proposal and calls ``prepare_execution_plan``;
    the kill-switch (``CONSECUTIVE_LOSSES``, no risk_ack) raises ``ExecutionPreflightError`` so the
    step returns ``EXCHANGE_EXECUTE_BLOCKED`` and ``place_order`` is never reached. ``place_order``
    is monkeypatched to raise to prove that. ``validate_order_request`` is stubbed to a no-network
    pass because for futures+demo it would otherwise call the exchange — keeping the test
    exchange-free and isolating the kill-switch as the sole blocking gate (not the stub).
    """

    async def fail_auto_execute(*_args, **_kwargs) -> str:
        raise AssertionError("resume with approved proposal must not auto-execute")

    async def fail_place_order(*_args, **_kwargs) -> dict:
        raise AssertionError("kill-switch must block before any exchange order is placed")

    async def stub_validate_order_request(**_kwargs) -> dict:
        # Exchange-free stub: futures+demo preflight would otherwise hit the network.
        # Passing here so the ONLY preflight blocker is the kill-switch under test.
        return {"passed": True, "errors": [], "exchange_mode": "demo", "market_type": "futures"}

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", fail_auto_execute)
    monkeypatch.setattr("app.agents.tools.exchange_tool.place_order", fail_place_order)
    monkeypatch.setattr(
        "app.services.execution_preflight.validate_order_request", stub_validate_order_request
    )

    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=_W24C_STEPS,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": False},
        input_payload={"symbol": "BTCUSDT"},
    )

    try:
        # Arm the consecutive-loss kill-switch (3 closed losses, no risk_ack on this project).
        await _seed_consecutive_loss_history(db_session, project.id)

        # 1) Reach the warmup pending-approval pause (closed_count=3 < warmup_trades=10).
        paused = await RunExecutor(db_session).execute(run.id, project.id)
        assert paused.status == "waiting_approval"
        assert paused.pause_reason == "warmup_pending_approval"
        assert paused.current_step_index == 1

        # 2) Seed a fully-valid APPROVED proposal for THIS run (test-only) so the resumed
        #    exchange_execute step finds it and proceeds into preflight.
        approved = TradeProposal(
            project_id=project.id,
            run_id=run.id,
            symbol="BTCUSDT",
            direction="LONG",
            entry_plan={"entry": 50000.0},
            take_profit=[{"price": 51000.0}],
            stop_loss=49000.0,
            position_size_usdt=100.0,
            status="APPROVED",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db_session.add(approved)
        await db_session.flush()

        # 3) Exercise the real approval/resume path.
        resumed = await RunExecutor(db_session).resume_approved(run.id, project.id)

        # 4) Resume advanced to execute_trade, which was BLOCKED by the kill-switch (no order).
        assert resumed.status == "completed"
        assert resumed.current_step_index == len(_W24C_STEPS)
        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        execute_step = next(s for s in run_steps if s.step_key == "execute_trade")
        assert execute_step.status == "completed"
        output = execute_step.output_json["output"]
        assert "EXCHANGE_EXECUTE_BLOCKED" in output
        assert "CONSECUTIVE_LOSSES" in output

        # 5) The preflight block flipped the proposal to REJECTED with the kill-switch reason.
        await db_session.refresh(approved)
        assert approved.status == "REJECTED"
        assert "CONSECUTIVE_LOSSES" in (approved.rejection_reason or "")

        # 6) No exchange order: no execution row for the approved proposal, no OPEN position.
        approved_execs = (
            (
                await db_session.execute(
                    select(TradeExecution).where(TradeExecution.proposal_id == approved.id)
                )
            )
            .scalars()
            .all()
        )
        assert approved_execs == []
        open_positions = (
            (
                await db_session.execute(
                    select(Position).where(
                        Position.project_id == project.id, Position.status == "OPEN"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert open_positions == []
    finally:
        # Explicit teardown of the seeded trading rows (project-cascade also covers these).
        await db_session.execute(delete(TradeJournal).where(TradeJournal.project_id == project.id))
        await db_session.execute(delete(Position).where(Position.project_id == project.id))
        await db_session.execute(
            delete(TradeExecution).where(TradeExecution.project_id == project.id)
        )
        await db_session.execute(
            delete(TradeProposal).where(TradeProposal.project_id == project.id)
        )
        await db_session.flush()
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_warmup_validation_only_completes_without_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """warmup_mode=validation_only → completes with a no-order result, no auto-execute, no rows."""
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        },
        {
            "key": "auto_winrate_gate",
            "kind": "winrate_trade_gate",
            "config": {
                "warmup_trades": 10,
                "skip_steps_on_auto": 1,
                "warmup_mode": "validation_only",
            },
        },
        {"key": "execute_trade", "kind": "exchange_execute"},
    ]

    async def fail_if_called(*_args, **_kwargs) -> str:
        raise AssertionError("validation_only warmup must not auto-execute")

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", fail_if_called)
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": False},
        input_payload={"symbol": "BTCUSDT"},
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "completed"
        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        gate = next(s for s in run_steps if s.step_key == "auto_winrate_gate")
        assert gate.output_json["meta"]["warmup_mode"] == "validation_only"
        assert gate.output_json["meta"]["auto_executed"] is False
        # execute_trade was skipped (skip_steps_on_auto), never run.
        assert not any(s.step_key == "execute_trade" for s in run_steps)
        executions, positions = await _execs_and_positions(db_session, project.id)
        assert executions == []
        assert positions == []
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_warmup_invalid_mode_fails_closed_to_pending(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid node-level warmup_mode fails closed to pending_approval (no order)."""
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        },
        {
            "key": "auto_winrate_gate",
            "kind": "winrate_trade_gate",
            "config": {
                "warmup_trades": 10,
                "skip_steps_on_auto": 1,
                "warmup_mode": "definitely_not_a_mode",
            },
        },
        {"key": "execute_trade", "kind": "exchange_execute"},
    ]

    async def fail_if_called(*_args, **_kwargs) -> str:
        raise AssertionError("invalid warmup_mode must fail closed (no auto-execute)")

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", fail_if_called)
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": False},
        input_payload={"symbol": "BTCUSDT"},
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "waiting_approval"
        assert completed.pause_reason == "warmup_pending_approval"
        executions, positions = await _execs_and_positions(db_session, project.id)
        assert executions == []
        assert positions == []
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_workflow_validation_only_dominates_warmup_auto_execute(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Top-level validation_only=True blocks execution even if warmup_mode=auto_execute."""
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        },
        {"key": "sage_review", "kind": "prompt", "agent_key": str(uuid4())},
        {
            "key": "auto_winrate_gate",
            "kind": "winrate_trade_gate",
            "config": {
                "warmup_trades": 10,
                "skip_steps_on_auto": 1,
                "warmup_mode": "auto_execute",
            },
        },
        {"key": "execute_trade", "kind": "exchange_execute"},
    ]

    async def fail_if_called(*_args, **_kwargs) -> str:
        raise AssertionError("validation_only run must not reach warmup auto-execution")

    monkeypatch.setattr(RunExecutor, "_auto_execute_trade_proposal", fail_if_called)
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
        definition_extra={"validation_only": True},
        input_payload={"symbol": "BTCUSDT"},
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "completed"
        output = json.loads(completed.output_text)
        assert output["validation_only"] is True
        assert output["no_order_placed"] is True
        executions, positions = await _execs_and_positions(db_session, project.id)
        assert executions == []
        assert positions == []
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_hawk_vote_gate_accepts_fenced_json_outputs(
    db_session: AsyncSession,
) -> None:
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        }
    ]
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={},
    )

    try:
        fenced_payload = """```json\n{\"agent\":\"hawk_trend\",\"vote\":\"BULLISH\",\"confidence\":75,\"invalidation_level\":65000.0}\n```"""
        for step_key, payload in {
            "hawk_trend": fenced_payload,
            "hawk_structure": fenced_payload.replace("hawk_trend", "hawk_structure"),
            "hawk_counter": fenced_payload.replace("hawk_trend", "hawk_counter").replace(
                "BULLISH", "NEUTRAL"
            ),
        }.items():
            db_session.add(
                RunStep(
                    run_id=run.id,
                    step_key=step_key,
                    step_kind="prompt",
                    status="completed",
                    output_json={"output": payload},
                )
            )
        await db_session.flush()

        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "completed"
        payload = json.loads(completed.output_text)
        assert payload["gate_result"] == "PASSED"
        assert payload["majority_direction"] == "BULLISH"
        assert payload["invalid_steps"] == []
        # DQ flags may be set (missing sources_used etc.) but must NOT block the gate.
        assert "dq_flags" in payload
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_hawk_vote_gate_reports_neutral_plurality(
    db_session: AsyncSession,
) -> None:
    """NEUTRAL/NEUTRAL/BEARISH → gate blocked (no BULLISH/BEARISH 2/3 majority),
    majority_direction reported as NEUTRAL (the plurality holder, not NO_MAJORITY)."""
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        }
    ]
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        hawk_votes={
            "hawk_trend": "NEUTRAL",
            "hawk_structure": "NEUTRAL",
            "hawk_counter": "BEARISH",
        },
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "blocked"
        assert completed.pause_reason == "hawk_vote_no_majority"

        gate_step = next(
            step
            for step in (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
            if step.step_key == "hawk_vote_gate"
        )
        gate_output = json.loads(gate_step.output_json["output"])
        assert gate_output["gate_result"] == "BLOCKED"
        # NEUTRAL holds plurality (2 vs BEARISH 1) — report NEUTRAL, not NO_MAJORITY.
        assert gate_output["majority_direction"] == "NEUTRAL"
        assert gate_output["vote_tally"]["NEUTRAL"] == 2
        assert gate_output["vote_tally"]["BEARISH"] == 1
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_hawk_vote_gate_records_dq_flags_without_blocking(
    db_session: AsyncSession,
) -> None:
    """Votes with missing data_quality / sources_used still count toward the majority.
    dq_flags is populated as a warning, but gate_passed is True on a 2/3 BULLISH majority."""
    steps = [
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend", "hawk_structure", "hawk_counter"]},
        }
    ]
    user, project, workflow, run = await _seed_scope(
        db_session,
        steps=steps,
        # Fixtures emit no data_quality / sources_used / market_data_snapshot — all DQ flags.
        hawk_votes={
            "hawk_trend": "BULLISH",
            "hawk_structure": "BULLISH",
            "hawk_counter": "NEUTRAL",
        },
    )

    try:
        completed = await RunExecutor(db_session).execute(run.id, project.id)
        assert completed.status == "completed"
        payload = json.loads(completed.output_text)
        assert payload["gate_result"] == "PASSED"
        assert payload["gate_passed"] is True
        assert payload["majority_direction"] == "BULLISH"
        # DQ flags must be recorded as warnings.
        assert isinstance(payload["dq_flags"], dict)
        assert len(payload["dq_flags"]) > 0
        # Legacy fields still present but empty (backward compat).
        assert payload["data_quality_failed_steps"] == []
    finally:
        await _cleanup_scope(db_session, user=user, project=project, workflow=workflow, run=run)
