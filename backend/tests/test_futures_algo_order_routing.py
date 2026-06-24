"""Phase 2C-B — every Binance DEMO/TESTNET/LIVE *futures* SL/TP order must use the Algo Order
API (/fapi/v1/algoOrder) via the hardened ``BinanceFuturesAdapter``, never the deprecated
``/fapi/v1/order`` conditional path (which returns -4120 and previously left a naked position
marked SUCCESS).

These tests prove:
  * ``_execute_futures_via_adapter`` places SL via ``place_stop_market_order`` and TP via
    ``place_take_profit_market_order`` (the Algo Order methods) — and exposes no generic
    conditional-order call.
  * The stop-loss is a HARD BLOCK: SL failure ⇒ ``ENTRY_FILLED_SL_FAILED`` (never ``SUCCESS``),
    ``needs_attention=True``, and no TP is attempted — so a caller that only persists a Position
    when ``execution_status == "SUCCESS"`` (autonomous ``run_executor`` and the API route) cannot
    mark a naked position EXECUTED.
  * ``_demo_execute`` (demo) and ``_exchange_execute`` (testnet/live) both delegate futures to the
    single safe helper — no second order-placement path with weaker safety.
  * The DEMO adapter base is demo-fapi, never the live endpoint.
  * The API execute route delegates futures demo/testnet to ``ExecutionService`` and never falls
    through to ``place_order``.

No real/demo/testnet/live order is placed — the adapter is always mocked, and the one real
adapter constructed (base check) makes no network call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.tools import exchange_tool


class _FakeAdapter:
    """Records the adapter methods invoked. Exposes ONLY the safe order methods — there is no
    generic ``create_order``/``/fapi/v1/order`` conditional entry point, so any attempt to place a
    conditional order off the Algo Order methods would raise ``AttributeError`` and fail the test.
    """

    def __init__(self, *, fail_sl: bool = False, fail_tp: bool = False) -> None:
        self.calls: list[tuple] = []
        self._fail_sl = fail_sl
        self._fail_tp = fail_tp

    async def __aenter__(self) -> _FakeAdapter:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def place_market_order(
        self, symbol: str, side: str, quantity: float, client_order_id: str | None = None
    ) -> dict:
        self.calls.append(("market", symbol, side.upper(), quantity))
        return {"orderId": 555111, "avgPrice": "100.0", "executedQty": str(quantity)}

    async def place_stop_market_order(
        self, symbol: str, side: str, quantity: float, stop_price: float, *a, **k
    ) -> dict:
        self.calls.append(("algo_sl", symbol, side.upper(), quantity, stop_price))
        if self._fail_sl:
            raise RuntimeError("-4120 simulated SL rejection")
        return {"algoId": 1000000000000001}

    async def place_take_profit_market_order(
        self, symbol: str, side: str, quantity: float, stop_price: float, *a, **k
    ) -> dict:
        self.calls.append(("algo_tp", symbol, side.upper(), quantity, stop_price))
        if self._fail_tp:
            raise RuntimeError("simulated TP rejection")
        return {"algoId": 1000000000000002}


def _patch_adapter(fake: _FakeAdapter):
    """Patch the adapter class imported inside ``_execute_futures_via_adapter`` (import is local
    to the function, so we patch the source module attribute)."""
    return patch(
        "app.crypto.exchanges.binance_futures_adapter.BinanceFuturesAdapter",
        return_value=fake,
    )


# ── _execute_futures_via_adapter: the single safe implementation ─────────────────────────────


@pytest.mark.anyio
async def test_futures_sl_uses_algo_api_and_succeeds_after_entry_plus_sl() -> None:
    fake = _FakeAdapter()
    with _patch_adapter(fake):
        result = await exchange_tool._execute_futures_via_adapter(
            symbol="SOLUSDT",
            side="buy",
            amount=0.11,
            price=100.0,
            stop_loss=90.0,
            take_profits=[110.0],
            mode_label="DEMO_FUTURES",
            exchange_label="binance_demo_futures",
        )

    kinds = [c[0] for c in fake.calls]
    assert kinds == ["market", "algo_sl", "algo_tp"]
    # SL closes a long via SELL on the Algo API
    sl_call = next(c for c in fake.calls if c[0] == "algo_sl")
    assert sl_call[2] == "SELL"
    assert sl_call[4] == 90.0
    assert result["execution_status"] == "SUCCESS"
    assert str(result["sl_order_id"]) == "1000000000000001"
    assert result["tp_order_ids"] == ["1000000000000002"]
    assert result["exchange"] == "binance_demo_futures"


@pytest.mark.anyio
async def test_futures_tp_uses_algo_api_take_profit_method() -> None:
    fake = _FakeAdapter()
    with _patch_adapter(fake):
        await exchange_tool._execute_futures_via_adapter(
            symbol="SOLUSDT",
            side="buy",
            amount=0.10,
            price=100.0,
            stop_loss=90.0,
            take_profits=[110.0, 120.0],
            mode_label="DEMO_FUTURES",
            exchange_label="binance_demo_futures",
        )
    tp_calls = [c for c in fake.calls if c[0] == "algo_tp"]
    assert len(tp_calls) == 2
    # All TP placement goes through the Algo take-profit method (never a /fapi/v1/order limit).
    assert all(c[2] == "SELL" for c in tp_calls)


@pytest.mark.anyio
async def test_futures_sl_failure_hard_blocks_no_success_and_no_tp() -> None:
    fake = _FakeAdapter(fail_sl=True)
    with _patch_adapter(fake):
        result = await exchange_tool._execute_futures_via_adapter(
            symbol="SOLUSDT",
            side="buy",
            amount=0.11,
            price=100.0,
            stop_loss=90.0,
            take_profits=[110.0],
            mode_label="DEMO_FUTURES",
            exchange_label="binance_demo_futures",
        )
    # Hard block: entry filled but SL could not be confirmed.
    assert result["execution_status"] == "ENTRY_FILLED_SL_FAILED"
    assert result["execution_status"] != "SUCCESS"
    assert result["needs_attention"] is True
    # No TP attempted after a failed SL.
    assert not any(c[0] == "algo_tp" for c in fake.calls)
    assert result["tp_order_ids"] == []


@pytest.mark.anyio
async def test_futures_tp_failure_is_non_blocking_still_success() -> None:
    fake = _FakeAdapter(fail_tp=True)
    with _patch_adapter(fake):
        result = await exchange_tool._execute_futures_via_adapter(
            symbol="SOLUSDT",
            side="buy",
            amount=0.11,
            price=100.0,
            stop_loss=90.0,
            take_profits=[110.0],
            mode_label="DEMO_FUTURES",
            exchange_label="binance_demo_futures",
        )
    # SL confirmed ⇒ SUCCESS even though TP failed (best-effort), with a recorded warning.
    assert result["execution_status"] == "SUCCESS"
    assert result["tp_order_ids"] == []
    assert result.get("tp_warnings")


# ── _demo_execute / _exchange_execute delegate futures to the safe helper ────────────────────


@pytest.mark.anyio
async def test_demo_execute_futures_delegates_to_safe_helper(monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "DEMO")
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    monkeypatch.setattr(exchange_tool, "MARKET_TYPE", "futures")

    spy = AsyncMock(return_value={"execution_status": "SUCCESS"})
    monkeypatch.setattr(exchange_tool, "_execute_futures_via_adapter", spy)

    await exchange_tool._demo_execute(
        symbol="SOLUSDT",
        side="buy",
        amount=0.11,
        order_type="market",
        price=100.0,
        stop_loss=90.0,
        take_profits=[110.0],
        notional_usdt=11.0,
        api_key=None,
        api_secret=None,
    )
    spy.assert_awaited_once()
    kwargs = spy.await_args.kwargs
    assert kwargs["mode_label"] == "DEMO_FUTURES"
    assert kwargs["exchange_label"] == "binance_demo_futures"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "sandbox,expected_mode,expected_label",
    [(True, "TESTNET", "binance_testnet"), (False, "LIVE", "binance_live")],
)
async def test_exchange_execute_binance_futures_delegates_to_safe_helper(
    monkeypatch, sandbox: bool, expected_mode: str, expected_label: str
) -> None:
    monkeypatch.setattr(exchange_tool, "MARKET_TYPE", "futures")
    spy = AsyncMock(return_value={"execution_status": "SUCCESS"})
    monkeypatch.setattr(exchange_tool, "_execute_futures_via_adapter", spy)

    await exchange_tool._exchange_execute(
        exchange_name="binance",
        symbol="SOLUSDT",
        side="buy",
        amount=0.11,
        order_type="market",
        price=100.0,
        stop_loss=90.0,
        take_profits=[110.0],
        api_key=None,
        api_secret=None,
        sandbox=sandbox,
    )
    spy.assert_awaited_once()
    kwargs = spy.await_args.kwargs
    assert kwargs["mode_label"] == expected_mode
    assert kwargs["exchange_label"] == expected_label


# ── DEMO never touches the live endpoint ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_demo_adapter_base_is_demo_not_live(monkeypatch) -> None:
    """A real adapter constructed under the demo profile targets demo-fapi, never live."""
    from app.crypto.exchanges.binance_futures_adapter import BinanceFuturesAdapter

    monkeypatch.setenv("BINANCE_ENVIRONMENT", "TESTNET")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    monkeypatch.delenv("BINANCE_FUTURES_BASE_URL", raising=False)

    adapter = BinanceFuturesAdapter()  # no network call in __init__
    try:
        assert adapter._base == "https://demo-fapi.binance.com"
        assert adapter._base.startswith("https://demo-")
    finally:
        await adapter.aclose()  # close the httpx client without any request


# ── API execute route centralizes futures demo/testnet on ExecutionService ───────────────────


@pytest.mark.anyio
@pytest.mark.parametrize("exchange_mode", ["demo", "testnet"])
async def test_execute_route_futures_delegates_to_execution_service(
    monkeypatch, exchange_mode: str
) -> None:
    from app.api.routes.v1 import trading

    monkeypatch.setenv("EXCHANGE_MODE", exchange_mode)
    monkeypatch.setenv("MARKET_TYPE", "futures")

    project_svc = MagicMock()
    project_svc.resolve_access = AsyncMock()
    db = AsyncMock()
    user = MagicMock()
    user.id = uuid4()

    sentinel = {"execution_status": "SUCCESS", "delegated_to": "ExecutionService"}
    svc_instance = MagicMock()
    svc_instance.execute = AsyncMock(return_value=sentinel)

    with (
        patch.object(trading, "ExecutionService", return_value=svc_instance),
        patch.object(trading, "place_order", AsyncMock()) as place_order_mock,
    ):
        result = await trading.execute_proposal(
            project_id=uuid4(),
            proposal_id=uuid4(),
            user=user,
            project_svc=project_svc,
            db=db,
        )

    assert result == sentinel
    svc_instance.execute.assert_awaited_once()
    # The route must NOT fall through to the legacy place_order path for futures demo/testnet.
    place_order_mock.assert_not_called()
