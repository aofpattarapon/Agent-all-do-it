"""Phase 2C-B — Layer B autonomous-path dry/mock validation.

Proves the *autonomous* ``run_executor`` execution steps (``_run_exchange_execute`` and
``_auto_execute_trade_proposal``) are transitively safe: they call the single centralized
``exchange_tool.place_order`` boundary (which, for DEMO futures, routes only through the Algo
Order adapter — proven in ``test_futures_algo_order_routing`` / ``test_demo_mode_boundary``) and
they persist a Position / mark the proposal EXECUTED **only** when
``execution_status == "SUCCESS"``.

Critical safety contract under test:
  * On a confirmed SUCCESS the step opens a Position and flips the proposal to EXECUTED.
  * On an ``ENTRY_FILLED_SL_FAILED`` (the stop-loss hard block) the step creates **no** OPEN
    Position and does **not** mark the proposal EXECUTED — so a naked, unprotected position can
    never be recorded as live by the autonomous path.

No real/demo/testnet/live order is placed: ``place_order`` is mocked, the DB is an in-memory
fake, and ``prepare_execution_plan`` is stubbed. Nothing touches the network.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.execution_preflight import ExecutionPlan
from app.services.run_executor import RunExecutor


class _Result:
    def __init__(self, obj: object) -> None:
        self._obj = obj

    def scalar_one_or_none(self) -> object:
        return self._obj


class _FakeDB:
    """Minimal AsyncSession stand-in: serves one proposal, records added objects."""

    def __init__(self, proposal: object) -> None:
        self._proposal = proposal
        self.added: list[object] = []

    async def execute(self, _stmt: object) -> _Result:
        return _Result(self._proposal)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def refresh(self, _obj: object) -> None:
        return None


def _make_proposal():
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        run_id=uuid4(),
        symbol="SOLUSDT",
        direction="long",
        stop_loss=90.0,
        status="APPROVED",
        rejection_reason=None,
        approved_at=None,
        full_proposal_md="thesis",
        news_summary="news",
        agent_vote_summary={"hawk": "long"},
        entry_plan={},
        take_profit=[110.0],
        position_size_usdt=11.0,
        raw_payload={},
    )


def _make_plan() -> ExecutionPlan:
    return ExecutionPlan(
        entry_price=100.0,
        take_profits=[110.0],
        size_usdt=11.0,
        amount=0.11,
        side="buy",
        direction="long",
        market_regime="trending",
        market_type="futures",
    )


_SUCCESS_RESULT = {
    "execution_status": "SUCCESS",
    "exchange": "binance_demo_futures",
    "mode": "DEMO_FUTURES",
    "order_id": "555111",
    "executed_price": 100.0,
    "size": 0.11,
    "sl_order_id": "1000000000000001",
    "tp_order_ids": ["1000000000000002"],
}

_SL_FAILED_RESULT = {
    "execution_status": "ENTRY_FILLED_SL_FAILED",
    "exchange": "binance_demo_futures",
    "mode": "DEMO_FUTURES",
    "order_id": "555111",
    "executed_price": 100.0,
    "size": 0.11,
    "sl_order_id": None,
    "tp_order_ids": [],
    "needs_attention": True,
    "error": "-4120 simulated SL rejection",
}


def _is_position(obj: object) -> bool:
    return type(obj).__name__ == "Position"


def _is_execution(obj: object) -> bool:
    return type(obj).__name__ == "TradeExecution"


# ── _run_exchange_execute (APPROVED-proposal autonomous step) ────────────────────────────────


@pytest.mark.anyio
async def test_run_exchange_execute_success_opens_position_and_marks_executed() -> None:
    proposal = _make_proposal()
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SUCCESS_RESULT))
    with (
        patch("app.agents.tools.exchange_tool.place_order", place_order),
        patch(
            "app.services.run_executor.prepare_execution_plan", AsyncMock(return_value=_make_plan())
        ),
    ):
        summary, meta = await ex._run_exchange_execute(proposal.project_id, proposal.run_id)

    # Calls the centralized safe boundary with the market/SL/TP contract.
    place_order.assert_awaited_once()
    kwargs = place_order.await_args.kwargs
    assert kwargs["order_type"] == "market"
    assert kwargs["stop_loss"] == 90.0
    assert kwargs["take_profits"] == [110.0]

    assert meta["execution_status"] == "SUCCESS"
    assert proposal.status == "EXECUTED"
    assert any(_is_position(o) for o in db.added), "SUCCESS must open a Position"
    execs = [o for o in db.added if _is_execution(o)]
    assert execs and execs[0].execution_status == "SUCCESS"


@pytest.mark.anyio
async def test_run_exchange_execute_sl_failure_no_position_not_executed() -> None:
    proposal = _make_proposal()
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SL_FAILED_RESULT))
    with (
        patch("app.agents.tools.exchange_tool.place_order", place_order),
        patch(
            "app.services.run_executor.prepare_execution_plan", AsyncMock(return_value=_make_plan())
        ),
    ):
        summary, meta = await ex._run_exchange_execute(proposal.project_id, proposal.run_id)

    assert meta["execution_status"] == "ENTRY_FILLED_SL_FAILED"
    assert meta["execution_status"] != "SUCCESS"
    # HARD BLOCK: no OPEN position recorded, proposal not marked EXECUTED.
    assert not any(_is_position(o) for o in db.added), "SL failure must NOT open a Position"
    assert proposal.status == "EXECUTION_FAILED"
    execs = [o for o in db.added if _is_execution(o)]
    assert execs and execs[0].execution_status == "ENTRY_FILLED_SL_FAILED"


# ── _auto_execute_trade_proposal (PENDING_APPROVAL → auto-approve → execute) ──────────────────


@pytest.mark.anyio
async def test_auto_execute_sl_failure_no_position_not_executed() -> None:
    proposal = _make_proposal()
    proposal.status = "PENDING_APPROVAL"
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SL_FAILED_RESULT))
    with (
        patch("app.agents.tools.exchange_tool.place_order", place_order),
        patch(
            "app.services.run_executor.prepare_execution_plan", AsyncMock(return_value=_make_plan())
        ),
    ):
        await ex._auto_execute_trade_proposal(proposal.project_id, proposal.run_id)

    place_order.assert_awaited_once()
    assert not any(_is_position(o) for o in db.added), "SL failure must NOT open a Position"
    assert proposal.status != "EXECUTED"
    execs = [o for o in db.added if _is_execution(o)]
    assert execs and execs[0].execution_status == "ENTRY_FILLED_SL_FAILED"


@pytest.mark.anyio
async def test_auto_execute_success_opens_position_and_marks_executed() -> None:
    proposal = _make_proposal()
    proposal.status = "PENDING_APPROVAL"
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SUCCESS_RESULT))
    with (
        patch("app.agents.tools.exchange_tool.place_order", place_order),
        patch(
            "app.services.run_executor.prepare_execution_plan", AsyncMock(return_value=_make_plan())
        ),
    ):
        await ex._auto_execute_trade_proposal(proposal.project_id, proposal.run_id)

    assert proposal.status == "EXECUTED"
    assert any(_is_position(o) for o in db.added), "SUCCESS must open a Position"


# ── Phase 6.14.T: single-use consecutive-loss ack consumption on the autonomous path ─────────


def _make_plan_ack(*, used: bool) -> ExecutionPlan:
    return ExecutionPlan(
        entry_price=100.0,
        take_profits=[110.0],
        size_usdt=11.0,
        amount=0.11,
        side="buy",
        direction="long",
        market_regime="trending",
        market_type="futures",
        consecutive_loss_ack_used=used,
    )


# Entry order never reached the exchange: no order_id, FAILED status.
_FAILED_RESULT = {
    "execution_status": "FAILED",
    "exchange": "binance_demo_futures",
    "mode": "DEMO_FUTURES",
    "error": "entry rejected",
    "sl_order_id": None,
    "tp_order_ids": [],
}


@pytest.mark.anyio
async def test_run_exchange_execute_consumes_ack_once_when_used_and_success() -> None:
    proposal = _make_proposal()
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    consume = AsyncMock(return_value=True)
    with (
        patch(
            "app.agents.tools.exchange_tool.place_order",
            AsyncMock(return_value=dict(_SUCCESS_RESULT)),
        ),
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(return_value=_make_plan_ack(used=True)),
        ),
        patch("app.services.risk_ack.consume_ack", consume),
    ):
        await ex._run_exchange_execute(proposal.project_id, proposal.run_id)

    consume.assert_awaited_once()
    assert consume.await_args.args[1] == proposal.project_id


@pytest.mark.anyio
async def test_run_exchange_execute_does_not_consume_ack_when_not_used() -> None:
    proposal = _make_proposal()
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    consume = AsyncMock(return_value=False)
    with (
        patch(
            "app.agents.tools.exchange_tool.place_order",
            AsyncMock(return_value=dict(_SUCCESS_RESULT)),
        ),
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(return_value=_make_plan_ack(used=False)),
        ),
        patch("app.services.risk_ack.consume_ack", consume),
    ):
        await ex._run_exchange_execute(proposal.project_id, proposal.run_id)

    consume.assert_not_awaited()


@pytest.mark.anyio
async def test_run_exchange_execute_consumes_ack_on_entry_filled_sl_failed() -> None:
    # The entry order DID reach the exchange (order_id present) — a naked position; the override
    # must still be burned so it cannot authorize a second order.
    proposal = _make_proposal()
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    consume = AsyncMock(return_value=True)
    with (
        patch(
            "app.agents.tools.exchange_tool.place_order",
            AsyncMock(return_value=dict(_SL_FAILED_RESULT)),
        ),
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(return_value=_make_plan_ack(used=True)),
        ),
        patch("app.services.risk_ack.consume_ack", consume),
    ):
        await ex._run_exchange_execute(proposal.project_id, proposal.run_id)

    consume.assert_awaited_once()


@pytest.mark.anyio
async def test_run_exchange_execute_does_not_consume_ack_on_failed_entry() -> None:
    # No order reached the exchange (FAILED, no order_id) → ack preserved for a legitimate retry.
    proposal = _make_proposal()
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    consume = AsyncMock(return_value=False)
    with (
        patch(
            "app.agents.tools.exchange_tool.place_order",
            AsyncMock(return_value=dict(_FAILED_RESULT)),
        ),
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(return_value=_make_plan_ack(used=True)),
        ),
        patch("app.services.risk_ack.consume_ack", consume),
    ):
        await ex._run_exchange_execute(proposal.project_id, proposal.run_id)

    consume.assert_not_awaited()


@pytest.mark.anyio
async def test_auto_execute_consumes_ack_once_when_used_and_success() -> None:
    proposal = _make_proposal()
    proposal.status = "PENDING_APPROVAL"
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    consume = AsyncMock(return_value=True)
    with (
        patch(
            "app.agents.tools.exchange_tool.place_order",
            AsyncMock(return_value=dict(_SUCCESS_RESULT)),
        ),
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(return_value=_make_plan_ack(used=True)),
        ),
        patch("app.services.risk_ack.consume_ack", consume),
    ):
        await ex._auto_execute_trade_proposal(proposal.project_id, proposal.run_id)

    consume.assert_awaited_once()
