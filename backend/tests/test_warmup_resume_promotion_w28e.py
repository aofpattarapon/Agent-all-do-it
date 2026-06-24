"""Phase 6.14.W28E — Warmup resume proposal persistence/promotion fix.

Covers the gap found in W28C-B: a ``warmup_pending_approval`` run resumed into ``execute_trade``
but no APPROVED proposal existed, so the order was (safely) skipped. The fix is persist-then-
promote:

  * compile-time kill-switch blocks now PERSIST a non-executable ``BLOCKED_KILL_SWITCH`` proposal
    (tested in ``test_proposal_min_notional``), and
  * an explicit warmup approval/resume re-validates that proposal through
    ``prepare_execution_plan`` (which re-runs the kill switch) and only then promotes it to
    ``APPROVED`` — so ``execute_trade`` can place exactly one order.

These tests exercise ``RunExecutor._promote_warmup_proposal`` directly with a fake DB. No real /
demo / testnet / live order is placed: ``prepare_execution_plan`` is mocked, the DB is in-memory.
The fail-closed contract is the focus — promotion must NEVER approve a proposal the re-check
rejects, and ``execute_trade`` keeps requiring ``status == "APPROVED"``.
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


class _FakeDB:
    """Minimal AsyncSession stand-in: serves one proposal, records flush calls."""

    def __init__(self, proposal: object) -> None:
        self._proposal = proposal
        self.flushes = 0

    async def execute(self, _stmt: object) -> _Result:
        return _Result(self._proposal)

    def add(self, _obj: object) -> None:  # pragma: no cover - not used here
        pass

    async def flush(self) -> None:
        self.flushes += 1


def _make_proposal(status: str = "PENDING_APPROVAL") -> SimpleNamespace:
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
    )


def _make_plan() -> ExecutionPlan:
    return ExecutionPlan(
        entry_price=64240.0,
        take_profits=[65720.0],
        size_usdt=50.0,
        amount=0.001,
        side="buy",
        direction="LONG",
        market_regime="NEUTRAL",
        market_type="futures",
    )


# ── promotion succeeds when the re-validation passes (kill switch clear or valid ack) ──────────


@pytest.mark.anyio
async def test_promote_warmup_proposal_pending_promotes_to_approved() -> None:
    proposal = _make_proposal(status="PENDING_APPROVAL")
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    with patch(
        "app.services.run_executor.prepare_execution_plan",
        AsyncMock(return_value=_make_plan()),
    ):
        promoted, reason = await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)

    assert promoted is True
    assert proposal.status == "APPROVED"
    assert proposal.approved_at is not None
    assert "promoted" in reason


@pytest.mark.anyio
async def test_promote_warmup_blocked_proposal_promotes_when_recheck_passes() -> None:
    """A BLOCKED_KILL_SWITCH proposal becomes APPROVED only if the re-check now passes.

    Models the intended risk_ack flow: the kill switch was armed at compile time (proposal stored
    BLOCKED_KILL_SWITCH); a valid single-use ack now exists, so the preflight re-check passes.
    """
    proposal = _make_proposal(status="BLOCKED_KILL_SWITCH")
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    with patch(
        "app.services.run_executor.prepare_execution_plan",
        AsyncMock(return_value=_make_plan()),
    ):
        promoted, reason = await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)

    assert promoted is True
    assert proposal.status == "APPROVED"


# ── fail-closed: re-check rejects → no approval, no order ──────────────────────────────────────


@pytest.mark.anyio
async def test_promote_warmup_blocked_proposal_stays_blocked_when_recheck_fails() -> None:
    """No valid ack and the kill switch still blocks → preflight fails → NOT approved."""
    proposal = _make_proposal(status="BLOCKED_KILL_SWITCH")
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    with patch(
        "app.services.run_executor.prepare_execution_plan",
        AsyncMock(side_effect=ExecutionPreflightError("kill switch: consecutive losses")),
    ):
        promoted, reason = await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)

    assert promoted is False
    assert proposal.status != "APPROVED"  # remains BLOCKED_KILL_SWITCH — never executable
    assert proposal.approved_at is None
    assert "preflight failed" in reason
    assert "WARMUP_PROMOTE_BLOCKED" in (proposal.rejection_reason or "")


@pytest.mark.anyio
async def test_promote_warmup_pending_proposal_stays_pending_when_recheck_fails() -> None:
    proposal = _make_proposal(status="PENDING_APPROVAL")
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    with patch(
        "app.services.run_executor.prepare_execution_plan",
        AsyncMock(side_effect=ExecutionPreflightError("preflight blocked")),
    ):
        promoted, _reason = await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)

    assert promoted is False
    assert proposal.status != "APPROVED"


# ── non-promotable states / missing proposal fail closed ────────────────────────────────────────


@pytest.mark.anyio
async def test_promote_warmup_no_proposal_fails_closed() -> None:
    db = _FakeDB(None)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    promoted, reason = await ex._promote_warmup_proposal(uuid4(), uuid4())

    assert promoted is False
    assert "no proposal" in reason


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["EXECUTED", "REJECTED", "EXPIRED", "NEEDS_ATTENTION", "DRAFT"])
async def test_promote_warmup_non_approvable_status_fails_closed(status: str) -> None:
    proposal = _make_proposal(status=status)
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    # prepare_execution_plan must never even be consulted for a non-approvable status.
    with patch(
        "app.services.run_executor.prepare_execution_plan",
        AsyncMock(side_effect=AssertionError("preflight must not run for non-approvable status")),
    ):
        promoted, reason = await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)

    assert promoted is False
    assert proposal.status == status  # unchanged
    assert "not approvable" in reason


@pytest.mark.anyio
async def test_promote_warmup_already_approved_is_idempotent() -> None:
    """An already-APPROVED proposal (e.g. double resume) is a no-op success, no re-validation."""
    proposal = _make_proposal(status="APPROVED")
    db = _FakeDB(proposal)
    ex = RunExecutor(db=db)  # type: ignore[arg-type]

    with patch(
        "app.services.run_executor.prepare_execution_plan",
        AsyncMock(side_effect=AssertionError("must not re-validate an already-APPROVED proposal")),
    ):
        promoted, reason = await ex._promote_warmup_proposal(proposal.project_id, proposal.run_id)

    assert promoted is True
    assert proposal.status == "APPROVED"
    assert "already APPROVED" in reason


# ── resume_approved wiring: promotion fires ONLY for the warmup pause reason ────────────────────


def _resume_executor(pause_reason: str) -> tuple[RunExecutor, AsyncMock]:
    """Build a RunExecutor whose resume_approved dependencies are stubbed.

    Returns (executor, promote_spy). The run is ``waiting_approval`` with the given pause_reason
    and no steps (so the step-completion branch is skipped). ``execute`` and metrics are stubbed so
    only the promotion wiring is under test.
    """
    run = SimpleNamespace(
        status="waiting_approval",
        pause_reason=pause_reason,
        current_step_index=0,
        paused_at=None,
    )
    ex = RunExecutor(db=AsyncMock())  # type: ignore[arg-type]
    ex._load_run = AsyncMock(return_value=run)  # type: ignore[method-assign]
    ex._load_steps = AsyncMock(return_value=[])  # type: ignore[method-assign]
    ex.execute = AsyncMock(return_value=run)  # type: ignore[method-assign]
    ex.metrics = SimpleNamespace(record_review_cycle=AsyncMock())  # type: ignore[assignment]
    promote_spy = AsyncMock(return_value=(True, "promoted to APPROVED"))
    ex._promote_warmup_proposal = promote_spy  # type: ignore[method-assign]
    return ex, promote_spy


@pytest.mark.anyio
async def test_resume_approved_warmup_calls_promotion() -> None:
    ex, promote_spy = _resume_executor("warmup_pending_approval")
    with patch("app.services.run_executor.run_repo") as repo:
        repo.update_run = AsyncMock()
        repo.update_run_step = AsyncMock()
        await ex.resume_approved(uuid4(), uuid4())

    promote_spy.assert_awaited_once()
    ex.execute.assert_awaited_once()  # run still continues to execute after promotion


@pytest.mark.anyio
async def test_resume_approved_non_warmup_skips_promotion() -> None:
    ex, promote_spy = _resume_executor("approval")
    with patch("app.services.run_executor.run_repo") as repo:
        repo.update_run = AsyncMock()
        repo.update_run_step = AsyncMock()
        await ex.resume_approved(uuid4(), uuid4())

    promote_spy.assert_not_awaited()  # legacy/manual approval path is untouched
    ex.execute.assert_awaited_once()
