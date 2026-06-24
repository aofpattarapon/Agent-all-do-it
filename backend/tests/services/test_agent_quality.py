"""Tests for AgentQualityService (Phase F).

These tests verify the read-only aggregation and the classification rules:
  * HAWK no-majority, SAGE veto, complete-reject, and limits are NOT agent failures.
  * handoff_validation_failed / handoff_contract_failed ARE agent failures.
  * invalid SL/TP markers are treated as validation failures.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.agent_quality import AgentQualityService


def _make_run(
    *,
    status: str,
    pause_reason: str = "",
    error_text: str = "",
    output_text: str = "",
    recovery_count: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        pause_reason=pause_reason,
        error_text=error_text,
        output_text=output_text,
        recovery_count=recovery_count,
        created_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )


def _make_step(
    *,
    agent_config_id,
    run_id,
    status: str = "completed",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        run_id=run_id,
        agent_config_id=agent_config_id,
        step_key="signal_gen",
        step_kind="prompt",
        status=status,
        created_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )


def _mock_db(
    agents: list[SimpleNamespace] | None = None,
    runs: list[SimpleNamespace] | None = None,
    steps: list[SimpleNamespace] | None = None,
    handoffs: list[SimpleNamespace] | None = None,
) -> MagicMock:
    """Return a mock DB that yields the four result sets in the order the service queries."""
    db = MagicMock()
    results = [agents or [], runs or [], steps or [], handoffs or []]
    index = 0

    async def _execute(_stmt):
        nonlocal index
        rows = results[index]
        index += 1
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    db.execute = AsyncMock(side_effect=_execute)
    return db


@pytest.mark.anyio
async def test_empty_project_returns_empty_quality() -> None:
    db = _mock_db(agents=[], runs=[], steps=[], handoffs=[])
    result = await AgentQualityService(db).aggregate(uuid4())
    assert result["items"] == []


@pytest.mark.anyio
async def test_agent_with_completed_steps_has_high_quality_rate() -> None:
    agent_id = uuid4()
    agent = SimpleNamespace(
        id=agent_id,
        name="Signal Gen",
        role="signal_generator",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    run = _make_run(status="completed")
    steps = [_make_step(agent_config_id=agent_id, run_id=run.id) for _ in range(4)]
    db = _mock_db(agents=[agent], runs=[run], steps=steps, handoffs=[])

    result = await AgentQualityService(db).aggregate(uuid4())
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["total_steps"] == 4
    assert item["successful_outputs"] == 4
    assert item["quality_rate"] == 100.0
    assert item["error_runs"] == 0


@pytest.mark.anyio
async def test_handoff_validation_failed_counts_as_validation_failure() -> None:
    agent_id = uuid4()
    agent = SimpleNamespace(
        id=agent_id,
        name="HAWK",
        role="hawk_gate",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    run = _make_run(status="blocked", pause_reason="handoff_validation_failed")
    steps = [_make_step(agent_config_id=agent_id, run_id=run.id)]
    db = _mock_db(agents=[agent], runs=[run], steps=steps, handoffs=[])

    result = await AgentQualityService(db).aggregate(uuid4())
    item = result["items"][0]
    assert item["validation_failures"] == 1
    assert item["error_runs"] == 1


@pytest.mark.anyio
async def test_handoff_contract_failed_counts_as_contract_failure() -> None:
    agent_id = uuid4()
    agent = SimpleNamespace(
        id=agent_id,
        name="Risk",
        role="risk_manager",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    run = _make_run(status="blocked", pause_reason="handoff_contract_failed")
    steps = [_make_step(agent_config_id=agent_id, run_id=run.id)]
    db = _mock_db(agents=[agent], runs=[run], steps=steps, handoffs=[])

    result = await AgentQualityService(db).aggregate(uuid4())
    item = result["items"][0]
    assert item["contract_failures"] == 1
    assert item["error_runs"] == 1


@pytest.mark.anyio
async def test_hawk_no_majority_is_not_agent_failure() -> None:
    agent_id = uuid4()
    agent = SimpleNamespace(
        id=agent_id,
        name="HAWK",
        role="hawk_gate",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    run = _make_run(status="blocked", pause_reason="hawk_vote_no_majority")
    steps = [_make_step(agent_config_id=agent_id, run_id=run.id)]
    db = _mock_db(agents=[agent], runs=[run], steps=steps, handoffs=[])

    result = await AgentQualityService(db).aggregate(uuid4())
    item = result["items"][0]
    assert item["validation_failures"] == 0
    assert item["contract_failures"] == 0
    assert item["error_runs"] == 0


@pytest.mark.anyio
async def test_sage_veto_is_not_agent_failure() -> None:
    agent_id = uuid4()
    agent = SimpleNamespace(
        id=agent_id,
        name="SAGE",
        role="sage",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    run = _make_run(status="blocked", pause_reason="sage_veto")
    steps = [_make_step(agent_config_id=agent_id, run_id=run.id)]
    db = _mock_db(agents=[agent], runs=[run], steps=steps, handoffs=[])

    result = await AgentQualityService(db).aggregate(uuid4())
    item = result["items"][0]
    assert item["error_runs"] == 0


@pytest.mark.anyio
async def test_limit_pause_is_not_agent_failure() -> None:
    agent_id = uuid4()
    agent = SimpleNamespace(
        id=agent_id,
        name="Risk",
        role="risk_manager",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    run = _make_run(status="blocked", pause_reason="max_open_positions")
    steps = [_make_step(agent_config_id=agent_id, run_id=run.id)]
    db = _mock_db(agents=[agent], runs=[run], steps=steps, handoffs=[])

    result = await AgentQualityService(db).aggregate(uuid4())
    item = result["items"][0]
    assert item["error_runs"] == 0


@pytest.mark.anyio
async def test_invalid_stop_loss_marker_is_agent_output_error() -> None:
    agent_id = uuid4()
    agent = SimpleNamespace(
        id=agent_id,
        name="Signal Gen",
        role="signal_generator",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    run = _make_run(
        status="failed",
        error_text="Execution preflight failed: invalid_short_stop_loss",
    )
    steps = [_make_step(agent_config_id=agent_id, run_id=run.id)]
    db = _mock_db(agents=[agent], runs=[run], steps=steps, handoffs=[])

    result = await AgentQualityService(db).aggregate(uuid4())
    item = result["items"][0]
    assert item["error_runs"] == 1
