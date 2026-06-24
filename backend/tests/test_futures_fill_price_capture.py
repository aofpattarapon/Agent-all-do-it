"""Phase 6.14.T — real fill price/qty capture for Binance USDⓈ-M futures MARKET orders.

USDⓈ-M MARKET fills settle ASYNCHRONOUSLY, so the synchronous POST ack from
``place_market_order`` frequently returns ``avgPrice="0.00000"`` / ``executedQty="0"``. The old
code did ``float(entry_order.get("avgPrice") or ... )`` — but ``"0.00000"`` is a non-empty,
truthy string, so it never fell through and persisted ``executed_price=0.0`` (the N3 bug, which
then made ``entry_price`` fall back to the proposal price).

These tests prove ``_execute_futures_via_adapter`` now resolves the real fill via, in order:
the ack → a ``get_order`` re-query → the live ``get_position`` entryPrice → the proposal price
(last resort) — and never persists 0.0.

No real/demo/testnet/live order is placed — the adapter is always a local fake.
"""

from __future__ import annotations

import pytest

from app.agents.tools import exchange_tool
from app.agents.tools.exchange_tool import _coerce_positive_float, _resolve_fill_price_qty


class _FillFakeAdapter:
    """Adapter fake whose MARKET ack is empty (avgPrice/executedQty == "0.00000"/"0").

    ``get_order`` and ``get_position`` return whatever the test configures so each fallback rung
    can be exercised independently.
    """

    def __init__(
        self, *, order_resp: dict | None = None, position_resp: list | None = None
    ) -> None:
        self._order_resp = order_resp if order_resp is not None else {}
        self._position_resp = position_resp if position_resp is not None else []
        self.calls: list[str] = []

    async def __aenter__(self) -> _FillFakeAdapter:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def place_market_order(self, symbol: str, side: str, quantity: float, *a, **k) -> dict:
        self.calls.append("market")
        # The empty async-fill ack: truthy "0.00000" strings that must NOT be persisted.
        return {"orderId": 9001, "avgPrice": "0.00000", "executedQty": "0"}

    async def get_order(self, symbol: str, order_id: str | int) -> dict:
        self.calls.append("get_order")
        return self._order_resp

    async def get_position(self, symbol: str) -> list:
        self.calls.append("get_position")
        return self._position_resp

    async def place_stop_market_order(self, *a, **k) -> dict:
        self.calls.append("algo_sl")
        return {"algoId": 1000000000000001}

    async def place_take_profit_market_order(self, *a, **k) -> dict:
        self.calls.append("algo_tp")
        return {"algoId": 1000000000000002}


def _patch_adapter(fake: _FillFakeAdapter):
    from unittest.mock import patch

    return patch(
        "app.crypto.exchanges.binance_futures_adapter.BinanceFuturesAdapter",
        return_value=fake,
    )


# ── _coerce_positive_float ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.00000", 0.0),  # the bug: truthy string, must coerce to 0.0
        ("0", 0.0),
        (0, 0.0),
        (-5.0, 0.0),  # non-positive treated as "no fill"
        (None, 0.0),
        ("", 0.0),
        ("not-a-number", 0.0),
        ("62493.0", 62493.0),
        (62493.0, 62493.0),
    ],
)
def test_coerce_positive_float(value: object, expected: float) -> None:
    assert _coerce_positive_float(value) == expected


# ── _resolve_fill_price_qty fallback ladder ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_fill_resolved_from_get_order_requery() -> None:
    fake = _FillFakeAdapter(order_resp={"avgPrice": "62493.0", "executedQty": "0.001"})
    entry = {"orderId": 9001, "avgPrice": "0.00000", "executedQty": "0"}
    price, qty, source = await _resolve_fill_price_qty(
        fake, symbol="BTCUSDT", entry_order=entry, price=62423.9, amount=0.001
    )
    assert price == 62493.0
    assert qty == 0.001
    assert source == "order_query"


@pytest.mark.anyio
async def test_fill_resolved_from_position_when_order_query_empty() -> None:
    fake = _FillFakeAdapter(
        order_resp={"avgPrice": "0.00000", "executedQty": "0"},
        position_resp=[{"entryPrice": "62493.0", "positionAmt": "-0.001"}],
    )
    entry = {"orderId": 9001, "avgPrice": "0.00000", "executedQty": "0"}
    price, qty, source = await _resolve_fill_price_qty(
        fake, symbol="BTCUSDT", entry_order=entry, price=62423.9, amount=0.001
    )
    assert price == 62493.0
    assert source == "position"
    # qty had no real source — falls back to the requested amount, never 0.0.
    assert qty == 0.001


@pytest.mark.anyio
async def test_fill_falls_back_to_proposal_price_never_zero() -> None:
    fake = _FillFakeAdapter(
        order_resp={"avgPrice": "0", "executedQty": "0"},
        position_resp=[{"entryPrice": "0.0"}],
    )
    entry = {"orderId": 9001, "avgPrice": "0.00000", "executedQty": "0"}
    price, qty, source = await _resolve_fill_price_qty(
        fake, symbol="BTCUSDT", entry_order=entry, price=62423.9, amount=0.001
    )
    assert price == 62423.9  # last-resort proposal price — crucially NOT 0.0
    assert qty == 0.001
    assert source == "proposal_fallback"


@pytest.mark.anyio
async def test_fill_used_directly_from_ack_when_populated_no_requery() -> None:
    fake = _FillFakeAdapter()
    entry = {"orderId": 9001, "avgPrice": "62493.0", "executedQty": "0.001"}
    price, qty, source = await _resolve_fill_price_qty(
        fake, symbol="BTCUSDT", entry_order=entry, price=62423.9, amount=0.001
    )
    assert (price, qty, source) == (62493.0, 0.001, "ack")
    assert "get_order" not in fake.calls  # no needless re-query when the ack already has the fill


# ── end-to-end through _execute_futures_via_adapter (the pipeline boundary) ──────────────────


@pytest.mark.anyio
async def test_execute_futures_persists_requeried_fill_not_zero() -> None:
    fake = _FillFakeAdapter(order_resp={"avgPrice": "62493.0", "executedQty": "0.001"})
    with _patch_adapter(fake):
        result = await exchange_tool._execute_futures_via_adapter(
            symbol="BTCUSDT",
            side="sell",
            amount=0.001,
            price=62423.9,
            stop_loss=63088.0,
            take_profits=[61095.7],
            mode_label="DEMO_FUTURES",
            exchange_label="binance_demo_futures",
        )
    assert result["execution_status"] == "SUCCESS"
    assert result["executed_price"] == 62493.0  # the real fill, not 0.0 and not the proposal price
    assert result["size"] == 0.001
    assert result["fill_price_source"] == "order_query"
