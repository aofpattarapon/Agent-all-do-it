"""Integration tests for the bounded HAWK invalid/truncated-JSON repair retry.

Drives RunExecutor.execute() against a real DB with a single HAWK prompt step
followed by the vote gate. The model output is mocked at the _run_step seam so
no LLM, exchange, or order path is touched.

Covers:
- output="{" (truncated) → exactly one bounded repair retry fires.
- retry success → the recovered valid JSON is persisted to the step and the run
  progresses past the HAWK step (the gate runs).
- retry failure → the step stays invalid, retry_count==1, block_reason recorded,
  and the run blocks fail-closed.
- retry_count never exceeds 1 and exactly one repair prompt is issued.
- no execution/order path is reached when HAWK output is invalid.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import AgentConfig, Project
from app.db.models.user import User
from app.db.models.workflow import Run, RunStep, Workflow
from app.db.session import get_worker_db_context
from app.services.run_executor import RunExecutor

_TRUNCATED = "{"
_MOCK_META = {
    "runtime": "ollama",
    "model": "gemma3:12b",
    "tokens_used": 4096,
    "max_tokens": 4096,
}


@pytest.fixture
async def db_session() -> AsyncSession:
    async with get_worker_db_context() as session:
        yield session


async def _seed(db: AsyncSession) -> tuple[User, Project, Workflow, Run]:
    user = User(
        email=f"hawk-retry-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="user",
        is_active=True,
        is_app_admin=False,
    )
    db.add(user)
    await db.flush()

    project = Project(user_id=user.id, name=f"Hawk Retry {uuid4().hex[:6]}")
    db.add(project)
    await db.flush()

    agent = AgentConfig(
        project_id=project.id,
        name="HAWK Trend",
        role="hawk_trend",
        system_prompt="You are a HAWK trend analyst. Return strict JSON only.",
        runtime_kind="ollama",
        model="gemma3:12b",
        max_tokens=4096,
    )
    db.add(agent)
    await db.flush()

    steps = [
        {
            "key": "hawk_trend",
            "kind": "prompt",
            "agent_key": str(agent.id),
            "config": {"prompt": "Analyze. Return strict JSON only."},
        },
        {
            "key": "hawk_vote_gate",
            "kind": "hawk_vote",
            "config": {"source_steps": ["hawk_trend"]},
        },
    ]
    workflow = Workflow(
        project_id=project.id,
        name=f"Hawk Retry WF {uuid4().hex[:6]}",
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
    return user, project, workflow, run


async def _cleanup(
    db: AsyncSession, *, user: User, project: Project, workflow: Workflow, run: Run
) -> None:
    await db.execute(delete(RunStep).where(RunStep.run_id == run.id))
    await db.execute(delete(Run).where(Run.id == run.id))
    await db.execute(delete(Workflow).where(Workflow.id == workflow.id))
    await db.execute(delete(Project).where(Project.id == project.id))
    await db.execute(delete(User).where(User.id == user.id))
    await db.flush()


def _patch_run_step(executor: RunExecutor, prompt_outputs: list[str], call_log: dict) -> None:
    """Patch _run_step to serve queued outputs for the HAWK prompt step and
    delegate every other step kind (the gate) to the real implementation."""
    real_run_step = executor._run_step
    queue = list(prompt_outputs)
    call_log.setdefault("prompt_calls", 0)
    call_log.setdefault("repair_calls", 0)

    async def fake_run_step(**kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("step_kind") != "prompt":
            return await real_run_step(**kwargs)
        call_log["prompt_calls"] += 1
        prompt = str((kwargs.get("config") or {}).get("prompt", ""))
        # Phase 6.7: repair prompt is either preserve mode ("Convert the previous
        # answer") or fresh-analysis mode ("Generate a fresh HAWK analysis") depending
        # on whether the previous output had a usable vote.
        if (
            "Convert the previous answer into valid JSON only" in prompt
            or "Generate a fresh HAWK analysis" in prompt
        ):
            call_log["repair_calls"] += 1
        out = queue.pop(0) if queue else _TRUNCATED
        return out, dict(_MOCK_META)

    executor._run_step = fake_run_step  # type: ignore[method-assign]


@pytest.mark.anyio
async def test_truncated_output_recovers_after_single_repair_retry(
    db_session: AsyncSession,
) -> None:
    user, project, workflow, run = await _seed(db_session)
    valid = json.dumps(
        {
            "agent": "hawk_trend",
            "vote": "BULLISH",
            "confidence": 72,
            "invalidation_level": 65000.0,
            "sources_used": ["pre-fetched market data"],
            "risk_flags": [],
            "symbol": "BTCUSDT",
            "analyzed_at": "2026-06-15T00:00:00Z",
            "data_quality": "REAL_MARKET_DATA",
            "market_data_snapshot": {"price": 107000.0},
        }
    )
    # 1 initial + 2 pre-existing plain re-runs (still "{"), then repair retry recovers.
    outputs = [_TRUNCATED, _TRUNCATED, _TRUNCATED, valid]
    call_log: dict = {}
    try:
        executor = RunExecutor(db_session)
        _patch_run_step(executor, outputs, call_log)
        await executor.execute(run.id, project.id)

        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        hawk = next(s for s in run_steps if s.step_key == "hawk_trend")
        recovered = json.loads(hawk.output_json["output"])
        assert recovered["vote"] == "BULLISH"  # recovered payload persisted
        meta = hawk.output_json["meta"]
        assert meta["retry_count"] == 1
        assert meta["retry_reason"] == "truncated_json"
        # Exactly one repair prompt was issued.
        assert call_log["repair_calls"] == 1
        # Progressed past the HAWK step → the gate step exists.
        assert any(s.step_key == "hawk_vote_gate" for s in run_steps)
    finally:
        await _cleanup(db_session, user=user, project=project, workflow=workflow, run=run)


@pytest.mark.anyio
async def test_persistent_truncation_blocks_fail_closed(db_session: AsyncSession) -> None:
    user, project, workflow, run = await _seed(db_session)
    call_log: dict = {}
    try:
        executor = RunExecutor(db_session)
        # Empty queue → fake always returns "{": retry also fails.
        _patch_run_step(executor, [], call_log)
        completed = await executor.execute(run.id, project.id)

        assert completed.status == "blocked"

        run_steps = (
            (await db_session.execute(select(RunStep).where(RunStep.run_id == run.id)))
            .scalars()
            .all()
        )
        hawk = next(s for s in run_steps if s.step_key == "hawk_trend")
        meta = hawk.output_json["meta"]
        assert meta["retry_count"] == 1  # never exceeds 1
        assert meta["retry_reason"] == "truncated_json"
        assert meta["block_reason"] == "hawk_unparseable_json_after_retry"
        # Exactly one repair prompt issued even though it failed.
        assert call_log["repair_calls"] == 1
        # No execution / order: no proposal/execution steps were produced.
        assert not any(s.step_key in {"execute_trade", "compile_proposal"} for s in run_steps)
    finally:
        await _cleanup(db_session, user=user, project=project, workflow=workflow, run=run)
