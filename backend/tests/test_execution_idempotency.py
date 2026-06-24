"""Trade-execution idempotency & locking (H5/H6).

A proposal must yield at most ONE successful execution: a retry, double-click, or concurrent
dispatch must not place a second entry order. The execute() path also serializes the
position-cap critical section and the per-proposal critical section with advisory locks.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter
from app.crypto.services.execution_service import ExecutionService
from app.db.locks import LockNamespace


def _result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.anyio
async def test_existing_success_execution_is_returned_without_placing_order() -> None:
    """If a SUCCESS execution already exists, execute() returns it and places NO new order."""
    existing = SimpleNamespace(
        id=uuid4(),
        order_id="ORD-123",
        sl_order_id="SL-1",
        tp_order_ids=["TP-1", "TP-2"],
        executed_price=100.0,
        size=0.5,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result(existing))
    svc = ExecutionService(db)

    with patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as adapter_cls:
        out = await svc.execute(uuid4(), uuid4(), uuid4())

    assert out["status"] == "SUCCESS"
    assert out["idempotent"] is True
    assert out["order_id"] == "ORD-123"
    assert out["execution_id"] == str(existing.id)
    # The exchange adapter must never be constructed / hit on the idempotent replay path.
    adapter_cls.assert_not_called()


@pytest.mark.anyio
async def test_execute_acquires_project_and_proposal_locks_first() -> None:
    """The per-project cap lock and per-proposal lock are acquired before any work."""
    proposal_id, project_id = uuid4(), uuid4()
    db = AsyncMock()
    # Short-circuit on an existing execution so we only assert the locking prologue.
    db.execute = AsyncMock(
        return_value=_result(
            SimpleNamespace(
                id=uuid4(),
                order_id="x",
                sl_order_id="",
                tp_order_ids=[],
                executed_price=1.0,
                size=1.0,
            )
        )
    )
    svc = ExecutionService(db)

    calls: list[LockNamespace] = []

    async def fake_lock(_db: object, namespace: LockNamespace, _value: object) -> None:
        calls.append(namespace)

    with patch("app.crypto.services.execution_service.advisory_xact_lock", side_effect=fake_lock):
        await svc.execute(proposal_id, project_id, uuid4())

    assert calls == [LockNamespace.POSITION_CAP, LockNamespace.PROPOSAL_EXECUTION]


@pytest.mark.anyio
async def test_get_proposal_uses_for_update_row_lock() -> None:
    """_get_proposal must lock the proposal row (FOR UPDATE) to serialize same-proposal executes."""
    captured: dict[str, object] = {}

    async def capture_execute(stmt: object) -> MagicMock:
        captured["stmt"] = stmt
        return _result(SimpleNamespace(id=uuid4()))

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=capture_execute)
    svc = ExecutionService(db)

    await svc._get_proposal(uuid4(), uuid4())

    # The compiled SELECT must carry a row lock (FOR UPDATE).
    assert captured["stmt"]._for_update_arg is not None


@pytest.mark.anyio
async def test_place_market_order_sets_deterministic_client_order_id() -> None:
    """A client_order_id maps to newClientOrderId; omitting it leaves the param out (compat)."""
    adapter = BinanceFuturesAdapter.__new__(BinanceFuturesAdapter)
    captured: dict[str, object] = {}

    async def fake_post(path: str, params: dict) -> dict:
        captured.clear()
        captured.update(params)
        return {"orderId": "1"}

    adapter._post = fake_post  # type: ignore[method-assign]

    await adapter.place_market_order("BTCUSDT", "BUY", 0.1, "pda-deadbeef")
    assert captured["newClientOrderId"] == "pda-deadbeef"

    await adapter.place_market_order("BTCUSDT", "BUY", 0.1)
    assert "newClientOrderId" not in captured


def test_client_order_id_fits_binance_limit() -> None:
    """f'pda-{uuid.hex}' must satisfy Binance's 36-char newClientOrderId limit + charset."""
    import re

    cid = f"pda-{uuid4().hex}"
    assert len(cid) <= 36
    assert re.fullmatch(r"[\.A-Za-z0-9:/_-]{1,36}", cid)
