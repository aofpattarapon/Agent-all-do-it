"""Unit tests for PositionLifecycleService.cleanup_orphan_protection_orders.

Phase 6.14.W6 — algo-aware orphan protection cleanup. These cover the cleanup path that
runs after a position closes: reconciling our recorded SL/TP order ids against BOTH the
regular open-orders surface AND the CONDITIONAL *algo* surface, then routing each confirmed
orphan to the matching cancel API. All exchange calls are mocked — no real exchange order is
ever placed, closed, or cancelled here.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.position_lifecycle import PositionLifecycleService

_ADAPTER_PATH = "app.crypto.exchanges.binance_futures_adapter.BinanceFuturesAdapter"


# ── Builders ──────────────────────────────────────────────────────────────────


def _make_service(exec_row: object) -> PositionLifecycleService:
    """Service whose DB returns ``exec_row`` for the TradeExecution lookup."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=exec_row)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    return PositionLifecycleService(db)


def _exec_row(
    *,
    mode: str = "DEMO_FUTURES",
    exchange: str = "binance_demo_futures",
    sl_id: str | None = None,
    tp_ids: list[str] | None = None,
) -> MagicMock:
    row = MagicMock()
    row.exchange = exchange
    row.raw_response = {"mode": mode}
    row.sl_order_id = sl_id
    row.tp_order_ids = tp_ids or []
    return row


def _position(symbol: str = "BTCUSDT") -> MagicMock:
    pos = MagicMock()
    pos.symbol = symbol
    pos.id = uuid.uuid4()
    pos.execution_id = uuid.uuid4()
    pos.stop_loss = 60000.0
    pos.take_profits = [70000.0]
    pos.status = "CLOSED"
    return pos


def _make_adapter(
    *,
    regular_ids: list[str] | None = None,
    algo_ids: list[str] | None = None,
    cancel_order_side: object = None,
    cancel_algo_side: object = None,
    algo_lookup_raises: Exception | None = None,
) -> AsyncMock:
    adapter = AsyncMock()
    adapter.get_open_orders = AsyncMock(
        return_value=[{"orderId": oid} for oid in (regular_ids or [])]
    )
    if algo_lookup_raises is not None:
        adapter.get_open_algo_orders = AsyncMock(side_effect=algo_lookup_raises)
    else:
        adapter.get_open_algo_orders = AsyncMock(
            return_value=[{"algoId": oid} for oid in (algo_ids or [])]
        )
    adapter.cancel_order = AsyncMock(side_effect=cancel_order_side)
    adapter.cancel_algo_order = AsyncMock(side_effect=cancel_algo_side)
    return adapter


def _patch_adapter(adapter: AsyncMock) -> object:
    """Patch BinanceFuturesAdapter so ``async with BinanceFuturesAdapter()`` yields ``adapter``."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=adapter)
    cm.__aexit__ = AsyncMock(return_value=None)
    return patch(_ADAPTER_PATH, MagicMock(return_value=cm))


# ── Algo-aware cleanup (the W6 fix) ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_cleanup_cancels_algo_tp_orphans_after_sl_close() -> None:
    # SL fired and closed the position; the 3 TP triggers are CONDITIONAL algo orders that
    # never show under get_open_orders. They must be cancelled via cancel_algo_order.
    sl_id, tp1, tp2, tp3 = "111", "773", "777", "783"
    pos = _position()
    svc = _make_service(_exec_row(sl_id=sl_id, tp_ids=[tp1, tp2, tp3]))
    adapter = _make_adapter(regular_ids=[], algo_ids=[tp1, tp2, tp3])

    with _patch_adapter(adapter):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert report["action"] == "cancelled"
    assert sorted(report["cancelled_algo"]) == [tp1, tp2, tp3]
    assert report["cancelled_regular"] == []
    # Regular cancel API never touched for algo orders.
    adapter.cancel_order.assert_not_called()
    assert adapter.cancel_algo_order.await_count == 3
    called_ids = {c.kwargs["algo_id"] for c in adapter.cancel_algo_order.await_args_list}
    assert called_ids == {tp1, tp2, tp3}
    # SL id (111) was already FINISHED, not resting → skipped, never cancelled.
    assert sl_id in report["skipped"]


@pytest.mark.anyio
async def test_cleanup_regular_orders_still_cancelled() -> None:
    # Regression: regular reduce-only orders still route through cancel_order, not algo.
    sl_id, tp1 = "200", "201"
    pos = _position()
    svc = _make_service(_exec_row(sl_id=sl_id, tp_ids=[tp1]))
    adapter = _make_adapter(regular_ids=[sl_id, tp1], algo_ids=[])

    with _patch_adapter(adapter):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert report["action"] == "cancelled"
    assert sorted(report["cancelled_regular"]) == [sl_id, tp1]
    assert report["cancelled_algo"] == []
    assert adapter.cancel_order.await_count == 2
    adapter.cancel_algo_order.assert_not_called()


@pytest.mark.anyio
async def test_cleanup_never_cancels_unrecorded_algo_order() -> None:
    # An unrelated active algo order exists on the symbol; it must never be cancelled.
    tp1 = "300"
    unrelated = "999999"
    pos = _position()
    svc = _make_service(_exec_row(sl_id=None, tp_ids=[tp1]))
    adapter = _make_adapter(regular_ids=[], algo_ids=[tp1, unrelated])

    with _patch_adapter(adapter):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert report["cancelled_algo"] == [tp1]
    assert adapter.cancel_algo_order.await_count == 1
    only_id = adapter.cancel_algo_order.await_args.kwargs["algo_id"]
    assert only_id == tp1
    assert unrelated not in report["cancelled"]
    assert unrelated not in report["orphans"]


@pytest.mark.anyio
async def test_cleanup_no_open_orders_is_safe_noop() -> None:
    # Nothing resting (already gone) → no cancel call, no error.
    pos = _position()
    svc = _make_service(_exec_row(sl_id="400", tp_ids=["401"]))
    adapter = _make_adapter(regular_ids=[], algo_ids=[])

    with _patch_adapter(adapter):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert report["action"] == "none_open"
    assert report["cancelled"] == []
    adapter.cancel_order.assert_not_called()
    adapter.cancel_algo_order.assert_not_called()
    assert sorted(report["skipped"]) == ["400", "401"]


@pytest.mark.anyio
async def test_cleanup_mixed_regular_and_algo_routes_each_correctly() -> None:
    # One recorded id is a regular order, two are algo orders → each path used once-correctly.
    reg, algo1, algo2 = "500", "501", "502"
    pos = _position()
    svc = _make_service(_exec_row(sl_id=reg, tp_ids=[algo1, algo2]))
    adapter = _make_adapter(regular_ids=[reg], algo_ids=[algo1, algo2])

    with _patch_adapter(adapter):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert report["cancelled_regular"] == [reg]
    assert sorted(report["cancelled_algo"]) == [algo1, algo2]
    adapter.cancel_order.assert_awaited_once()
    assert adapter.cancel_algo_order.await_count == 2


@pytest.mark.anyio
async def test_cleanup_one_algo_cancel_fails_others_proceed_no_broad_cancel() -> None:
    # If one algo cancel fails, the failure is reported but the others still cancel; the
    # function never escalates to a broad cancel.
    a, b, c = "600", "601", "602"
    pos = _position()
    svc = _make_service(_exec_row(sl_id=None, tp_ids=[a, b, c]))

    def _side(*, algo_id: str) -> dict:
        if algo_id == b:
            raise RuntimeError("exchange rejected")
        return {"code": "200", "msg": "success"}

    adapter = _make_adapter(regular_ids=[], algo_ids=[a, b, c], cancel_algo_side=_side)

    with _patch_adapter(adapter):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert sorted(report["cancelled_algo"]) == [a, c]
    assert report["failed"] == [{"order_id": b, "kind": "algo", "error": "exchange rejected"}]
    # Best-effort per order: all three were attempted, none broadened.
    assert adapter.cancel_algo_order.await_count == 3
    assert not hasattr(adapter, "cancel_all_open_orders") or (
        adapter.cancel_all_open_orders.await_count == 0
    )


@pytest.mark.anyio
async def test_cleanup_algo_lookup_error_is_non_fatal_for_regular_path() -> None:
    # If the algo endpoint errors, regular cleanup still proceeds and the error is recorded.
    reg = "700"
    pos = _position()
    svc = _make_service(_exec_row(sl_id=reg, tp_ids=["701"]))
    adapter = _make_adapter(
        regular_ids=[reg], algo_ids=[], algo_lookup_raises=RuntimeError("algo endpoint down")
    )

    with _patch_adapter(adapter):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert report["cancelled_regular"] == [reg]
    assert report["algo_lookup_error"] == "algo endpoint down"
    assert report["algo_orphans"] == []


# ── Safety branches (mode-gated) ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_cleanup_live_is_detect_only_never_cancels() -> None:
    # LIVE (real money): detect and report only; the adapter is never even constructed.
    pos = _position()
    svc = _make_service(
        _exec_row(mode="LIVE", exchange="binance_live", sl_id="800", tp_ids=["801"])
    )
    fake_cls = MagicMock()

    with patch(_ADAPTER_PATH, fake_cls):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert report["action"] == "detected_only_live"
    assert sorted(report["orphans"]) == ["800", "801"]
    fake_cls.assert_not_called()


@pytest.mark.anyio
async def test_cleanup_paper_is_skipped_no_exchange_call() -> None:
    # PAPER: not submitted to any exchange → nothing to clean, adapter never constructed.
    pos = _position()
    svc = _make_service(
        _exec_row(mode="PAPER", exchange="paper_trade", sl_id="900", tp_ids=["901"])
    )
    fake_cls = MagicMock()

    with patch(_ADAPTER_PATH, fake_cls):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert report["action"] == "skipped_simulated"
    fake_cls.assert_not_called()


@pytest.mark.anyio
async def test_cleanup_no_execution_row_is_skipped() -> None:
    pos = _position()
    svc = _make_service(None)
    fake_cls = MagicMock()

    with patch(_ADAPTER_PATH, fake_cls):
        report = await svc.cleanup_orphan_protection_orders(pos)

    assert report["action"] == "skipped_no_execution"
    fake_cls.assert_not_called()
