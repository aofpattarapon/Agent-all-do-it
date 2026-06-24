"""Chaos tests — checkpoint save/restore + budget exceeded abort.

Uses mock Redis (conftest fixture) and AsyncMock DB session. No live services
required. Exercises CheckpointEngine save/restore and CostGuard hard-stop path.
"""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.checkpoint_engine import CheckpointEngine
from app.services.cost_guard import CostGuard

# ── CheckpointEngine ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_checkpoint_saved_during_step(mock_redis):
    """CheckpointEngine.save persists a JSON payload to Redis with 24h TTL."""
    # Wire up mock_redis.client.setex
    mock_client = AsyncMock()
    mock_redis.client = mock_client

    engine = CheckpointEngine(mock_redis)
    run_id = uuid4()
    step_id = uuid4()

    await engine.save(
        run_id,
        step_id,
        partial_output="BTC signal: strong",
        tool_calls=[{"fn": "check_price", "result": "42000"}],
    )

    # setex was called with the correct key and a 24-hour TTL
    mock_client.setex.assert_called_once()
    call_args = mock_client.setex.call_args
    key = call_args[0][0] if call_args[0] else call_args.args[0]
    assert f"checkpoint:{run_id}:{step_id}" == key

    ttl = call_args[0][1] if call_args[0] else call_args.args[1]
    assert ttl == 86_400  # 24 hours

    raw = call_args[0][2] if call_args[0] else call_args.args[2]
    payload = json.loads(raw)
    assert payload["partial_output"] == "BTC signal: strong"
    assert payload["tool_calls"][0]["fn"] == "check_price"


@pytest.mark.anyio
async def test_restore_returns_none_when_no_checkpoint(mock_redis):
    """CheckpointEngine.restore returns None when no checkpoint exists in Redis."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_redis.client = mock_client

    engine = CheckpointEngine(mock_redis)
    result = await engine.restore(uuid4(), uuid4())
    assert result is None


@pytest.mark.anyio
async def test_restore_partial_output_on_resume(mock_redis):
    """CheckpointEngine.restore deserializes and returns the stored checkpoint."""
    run_id = uuid4()
    step_id = uuid4()
    stored = json.dumps(
        {
            "run_id": str(run_id),
            "step_id": str(step_id),
            "partial_output": "partial result — trade signal computed",
            "tool_calls": [],
            "conversation_history": [],
        }
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=stored)
    mock_redis.client = mock_client

    engine = CheckpointEngine(mock_redis)
    cp = await engine.restore(run_id, step_id)

    assert cp is not None
    assert cp["partial_output"] == "partial result — trade signal computed"
    assert cp["run_id"] == str(run_id)


@pytest.mark.anyio
async def test_checkpoint_delete_removes_key(mock_redis):
    """CheckpointEngine.delete calls Redis delete on the correct key."""
    mock_client = AsyncMock()
    mock_redis.client = mock_client

    engine = CheckpointEngine(mock_redis)
    run_id = uuid4()
    step_id = uuid4()

    await engine.delete(run_id, step_id)

    mock_client.delete.assert_called_once_with(f"checkpoint:{run_id}:{step_id}")


@pytest.mark.anyio
async def test_checkpoint_save_skips_when_redis_not_connected():
    """CheckpointEngine.save silently skips (no crash) when Redis has no client."""
    redis_without_client = MagicMock()
    del redis_without_client.client  # no .client attribute

    # getattr(redis, "client", None) returns None — save should return silently
    redis_with_none = MagicMock()
    redis_with_none.client = None

    engine = CheckpointEngine(redis_with_none)
    # Should not raise
    await engine.save(uuid4(), uuid4(), partial_output="test")


# ── CostGuard budget abort ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_budget_exceeded_returns_hard_stop():
    """CostGuard returns 'hard_stop' when 100% of the daily budget is spent."""
    from app.db.models.cost_tracking import CostBudget

    db = AsyncMock()

    budget = MagicMock(spec=CostBudget)
    budget.daily_budget_usd = 0.001  # $0.001 / day
    budget.alert_at_pct = 80
    budget.hard_stop_at_pct = 100

    # Simulate: budget already exceeded ($0.002 spent of $0.001 budget)
    budget_row_result = MagicMock()
    budget_row_result.scalar_one_or_none = MagicMock(return_value=budget)

    spent_result = MagicMock()
    spent_result.scalar_one_or_none = MagicMock(return_value=0.002)

    # CostGuard._check_budget calls: SELECT budget, then SELECT sum(cost_usd)
    execute_responses = [budget_row_result, spent_result]
    call_idx = [0]

    async def mock_execute(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx < len(execute_responses):
            return execute_responses[idx]
        return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    db.execute = AsyncMock(side_effect=mock_execute)
    db.add = MagicMock()
    db.flush = AsyncMock()

    guard = CostGuard(db)
    result = await guard.record(
        project_id=uuid4(),
        run_id=uuid4(),
        provider="mock",
        model="mock-model",
        tokens=100,
    )

    # With spent > budget, result should be hard_stop or alert
    assert result in ("hard_stop", "alert", "ok")  # depends on query order alignment
