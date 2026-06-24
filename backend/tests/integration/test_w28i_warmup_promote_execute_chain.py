"""Phase 6.14.W28I — Staging-only W28E promotion → execute integration test.

W28F and W28G were both (correctly) blocked at the HAWK vote gate because the live market was
neutral, so the W28E persist-then-promote → execute path was never exercised end-to-end against a
real run. This test exercises that exact chain *deterministically* — with a mocked 2/3 HAWK
majority assumed upstream (the gate is NOT touched here) — by driving the two real W28E methods
back-to-back on a single shared proposal:

    compile-time persistence  →  ``_promote_warmup_proposal`` (resume_approved path)
                              →  proposal APPROVED  →  ``_run_exchange_execute``  →  mocked exchange

Nothing here touches production: the HAWK production gate/threshold is never imported or modified,
``place_order`` is mocked (no real / demo / testnet / live order leaves the process),
``prepare_execution_plan`` and ``risk_ack.consume_ack`` are mocked, and the DB is an in-memory
status-aware fake. The focus is the **cross-segment safety invariants** the per-segment unit tests
(``test_warmup_resume_promotion_w28e`` / ``test_run_executor_exchange_execute_autonomous``) cannot
assert on their own:

  * a kill-switch-blocked proposal with NO valid ack flows resume → promote(fail) → execute(skip)
    and places ZERO orders;
  * the single-use consecutive-loss ack is NOT burned at promotion but IS burned once at execute;
  * a second execute attempt cannot re-place the order or re-burn the ack (idempotency).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.execution_preflight import ExecutionPlan, ExecutionPreflightError
from app.services.run_executor import RunExecutor


class _Result:
    def __init__(self, obj: object) -> None:
        self._obj = obj

    def scalar_one_or_none(self) -> object:
        return self._obj


class _StatusAwareDB:
    """In-memory AsyncSession stand-in that honours the execute-step's ``status == APPROVED``
    filter.

    ``_promote_warmup_proposal`` selects the run's proposal with NO status filter; the
    ``_run_exchange_execute`` step adds ``TradeProposal.status == "APPROVED"`` to the WHERE clause.
    A plain fake that always returns the proposal would let a non-APPROVED proposal reach the
    execute step — defeating the whole fail-closed contract under test. So this fake inspects the
    statement's WHERE clause: a status-filtered query returns the proposal only while it is
    actually APPROVED (else ``None`` → the step skips), exactly like the real DB.
    """

    def __init__(self, proposal: object | None) -> None:
        self._proposal = proposal
        self.added: list[object] = []
        self.flushes = 0

    async def execute(self, stmt: object) -> _Result:
        wc = getattr(stmt, "whereclause", None)
        where_sql = str(wc) if wc is not None else ""
        if "status" in where_sql:  # the exchange_execute APPROVED-only lookup
            status = getattr(self._proposal, "status", None)
            return _Result(self._proposal if status == "APPROVED" else None)
        return _Result(self._proposal)  # the promotion lookup (no status filter)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1

    async def refresh(self, _obj: object) -> None:
        return None


def _make_proposal(status: str = "BLOCKED_KILL_SWITCH") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        run_id=uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        stop_loss=63500.0,
        status=status,
        rejection_reason=None,
        approved_at=None,
        entry_plan={"primary_entry": 64240.0},
        take_profit=[{"tp_level": 65720.0}],
        position_size_usdt=50.0,
        full_proposal_md="thesis",
        news_summary="news",
        agent_vote_summary={"hawk_trend": "BULLISH", "hawk_structure": "BULLISH"},
        raw_payload={},
    )


def _make_plan(*, ack_used: bool = False) -> ExecutionPlan:
    return ExecutionPlan(
        entry_price=64240.0,
        take_profits=[65720.0],
        size_usdt=50.0,
        amount=0.001,
        side="buy",
        direction="LONG",
        market_regime="BULLISH",
        market_type="futures",
        consecutive_loss_ack_used=ack_used,
    )


# A confirmed entry+SL+TP fill from the mocked exchange (no network).
_SUCCESS_RESULT = {
    "execution_status": "SUCCESS",
    "exchange": "binance_demo_futures",
    "mode": "DEMO_FUTURES",
    "order_id": "777222",
    "executed_price": 64240.0,
    "size": 0.001,
    "sl_order_id": "1000000000000001",
    "tp_order_ids": ["1000000000000002"],
}


def _is(obj: object, name: str) -> bool:
    return type(obj).__name__ == name


# ── Scenario 1 — happy path: warmup resume promotes, then executes via mock exchange ───────────


@pytest.mark.anyio
async def test_w28i_resume_promote_then_execute_places_one_order_with_sl_tp() -> None:
    """BLOCKED_KILL_SWITCH proposal + valid ack → promote re-validates to APPROVED → execute places
    exactly one order carrying the SL and TP ladder, opens a Position, marks the proposal EXECUTED.
    """
    proposal = _make_proposal(status="BLOCKED_KILL_SWITCH")
    db = _StatusAwareDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SUCCESS_RESULT))
    consume = AsyncMock(return_value=True)
    with (
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(return_value=_make_plan(ack_used=True)),
        ),
        patch("app.agents.tools.exchange_tool.place_order", place_order),
        patch("app.services.risk_ack.consume_ack", consume),
    ):
        # 1) promotion (the resume_approved warmup branch) — re-validation passes, no order yet.
        promoted, reason = await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)
        assert promoted is True
        assert proposal.status == "APPROVED"
        assert proposal.approved_at is not None
        place_order.assert_not_awaited()  # promotion NEVER places an order
        consume.assert_not_awaited()  # promotion NEVER burns the ack

        # 2) execute step — finds the now-APPROVED proposal and places exactly one order.
        summary, meta = await ex._run_exchange_execute(proposal.project_id, proposal.run_id)

    place_order.assert_awaited_once()
    kwargs = place_order.await_args.kwargs
    assert kwargs["order_type"] == "market"
    assert kwargs["stop_loss"] == 63500.0  # SL forwarded to the exchange request
    assert kwargs["take_profits"] == [65720.0]  # TP ladder forwarded
    assert kwargs["notional_usdt"] == 50.0

    assert meta["execution_status"] == "SUCCESS"
    assert proposal.status == "EXECUTED"
    assert sum(_is(o, "TradeExecution") for o in db.added) == 1
    assert sum(_is(o, "Position") for o in db.added) == 1
    consume.assert_awaited_once()  # ack burned exactly once, at execute time


# ── Scenario 2 — kill switch blocked, no ack: promote fails, execute skips, zero orders ────────


@pytest.mark.anyio
async def test_w28i_blocked_without_ack_fails_closed_no_order() -> None:
    """No valid ack → preflight re-check rejects at promotion → proposal stays BLOCKED_KILL_SWITCH →
    execute finds no APPROVED proposal and places no order. Fail-closed end to end."""
    proposal = _make_proposal(status="BLOCKED_KILL_SWITCH")
    db = _StatusAwareDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SUCCESS_RESULT))
    consume = AsyncMock(return_value=True)
    with (
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(side_effect=ExecutionPreflightError("kill switch: consecutive losses")),
        ),
        patch("app.agents.tools.exchange_tool.place_order", place_order),
        patch("app.services.risk_ack.consume_ack", consume),
    ):
        promoted, reason = await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)
        assert promoted is False
        assert proposal.status == "BLOCKED_KILL_SWITCH"  # never executable
        assert proposal.approved_at is None
        assert "WARMUP_PROMOTE_BLOCKED" in (proposal.rejection_reason or "")

        summary, meta = await ex._run_exchange_execute(proposal.project_id, proposal.run_id)

    assert meta.get("skipped") is True
    assert "no APPROVED proposal" in summary
    place_order.assert_not_awaited()  # NO order ever placed
    consume.assert_not_awaited()  # ack preserved for a legitimate retry
    assert not any(_is(o, "TradeExecution") for o in db.added)
    assert not any(_is(o, "Position") for o in db.added)


# ── Scenario 3 — ack single-use: not burned at promote, burned once at execute, not reusable ───


@pytest.mark.anyio
async def test_w28i_ack_not_consumed_at_promotion_consumed_once_at_execute() -> None:
    proposal = _make_proposal(status="BLOCKED_KILL_SWITCH")
    db = _StatusAwareDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SUCCESS_RESULT))
    consume = AsyncMock(return_value=True)
    with (
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(return_value=_make_plan(ack_used=True)),
        ),
        patch("app.agents.tools.exchange_tool.place_order", place_order),
        patch("app.services.risk_ack.consume_ack", consume),
    ):
        await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)
        assert consume.await_count == 0  # promotion must not consume the single-use ack

        await ex._run_exchange_execute(proposal.project_id, proposal.run_id)
        assert consume.await_count == 1  # consumed exactly once at execute

        # Second execute attempt: proposal is now EXECUTED → no APPROVED proposal → cannot reuse.
        await ex._run_exchange_execute(proposal.project_id, proposal.run_id)
        assert consume.await_count == 1  # still one — ack never re-consumed
    assert place_order.await_count == 1


# ── Scenario 4 — idempotency: double execute → one order, one execution row ─────────────────────


@pytest.mark.anyio
async def test_w28i_double_execute_places_single_order_single_execution_row() -> None:
    proposal = _make_proposal(status="APPROVED")
    db = _StatusAwareDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SUCCESS_RESULT))
    with (
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(return_value=_make_plan(ack_used=False)),
        ),
        patch("app.agents.tools.exchange_tool.place_order", place_order),
        patch("app.services.risk_ack.consume_ack", AsyncMock(return_value=False)),
    ):
        summary1, meta1 = await ex._run_exchange_execute(proposal.project_id, proposal.run_id)
        summary2, meta2 = await ex._run_exchange_execute(proposal.project_id, proposal.run_id)

    assert meta1["execution_status"] == "SUCCESS"
    assert proposal.status == "EXECUTED"
    assert meta2.get("skipped") is True  # second attempt finds no APPROVED proposal
    place_order.assert_awaited_once()  # no duplicate exchange call
    assert sum(_is(o, "TradeExecution") for o in db.added) == 1
    assert sum(_is(o, "Position") for o in db.added) == 1


# ── Scenario 5 — regression: execute with no APPROVED proposal skips safely (no order) ──────────


@pytest.mark.anyio
async def test_w28i_execute_with_no_proposal_skips_safely() -> None:
    db = _StatusAwareDB(None)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SUCCESS_RESULT))
    with (
        patch("app.agents.tools.exchange_tool.place_order", place_order),
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(side_effect=AssertionError("preflight must not run when no proposal exists")),
        ),
    ):
        summary, meta = await ex._run_exchange_execute(uuid4(), uuid4())

    assert meta.get("skipped") is True
    place_order.assert_not_awaited()
    assert db.added == []


@pytest.mark.anyio
async def test_w28i_non_approvable_proposal_cannot_be_promoted_then_executed() -> None:
    """An already-EXECUTED proposal is non-approvable: promotion refuses without even re-validating,
    and the execute step still finds nothing APPROVED to place. No re-entry on a closed trade."""
    proposal = _make_proposal(status="EXECUTED")
    db = _StatusAwareDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    place_order = AsyncMock(return_value=dict(_SUCCESS_RESULT))
    with (
        patch(
            "app.services.run_executor.prepare_execution_plan",
            AsyncMock(
                side_effect=AssertionError("preflight must not run for non-approvable status")
            ),
        ),
        patch("app.agents.tools.exchange_tool.place_order", place_order),
    ):
        promoted, reason = await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)
        assert promoted is False
        assert "not approvable" in reason
        assert proposal.status == "EXECUTED"  # unchanged

        # EXECUTED != APPROVED → execute step skips; no second order on the same proposal.
        summary, meta = await ex._run_exchange_execute(proposal.project_id, proposal.run_id)
        assert meta.get("skipped") is True
    place_order.assert_not_awaited()
