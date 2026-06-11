"""Integration tests for the code-level HAWK majority gate."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

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

    workflow = Workflow(
        project_id=project.id,
        name=f"Hawk Vote Workflow {uuid4().hex[:6]}",
        trigger_kind="manual",
        definition_json={"steps": steps},
    )
    db.add(workflow)
    await db.flush()

    run = Run(project_id=project.id, workflow_id=workflow.id, trigger="manual", input_payload_json={})
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
                            "invalidation_level": 100.0,
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
        assert "no 2/3 directional majority" in completed.error_text

        run_steps = (
            await db_session.execute(select(RunStep).where(RunStep.run_id == run.id))
        ).scalars().all()
        assert any(step.step_key == "hawk_vote_gate" for step in run_steps)
        assert not any(step.step_key == "sage_review" for step in run_steps)

        gate_step = next(step for step in run_steps if step.step_key == "hawk_vote_gate")
        gate_output = json.loads(gate_step.output_json["output"])
        assert gate_output["gate_result"] == "BLOCKED"
        assert gate_output["majority_direction"] == "NO_MAJORITY"
    finally:
        await _cleanup_scope(
            db_session, user=user, project=project, workflow=workflow, run=run
        )


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
        await _cleanup_scope(
            db_session, user=user, project=project, workflow=workflow, run=run
        )


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
        fenced_payload = """```json\n{\"agent\":\"hawk_trend\",\"vote\":\"BULLISH\",\"confidence\":75}\n```"""
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
    finally:
        await _cleanup_scope(
            db_session, user=user, project=project, workflow=workflow, run=run
        )
