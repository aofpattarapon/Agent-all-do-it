"""Unit tests for ExecutionService — adapter and DB mocked."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TRADING_MODE", "TESTNET")
os.environ.setdefault("EXCHANGE_MODE", "testnet")
os.environ.setdefault("LIVE_TRADING_ENABLED", "false")
os.environ.setdefault("BINANCE_FUTURES_BASE_URL", "https://demo-fapi.binance.com")
os.environ.setdefault("BINANCE_ENVIRONMENT", "TESTNET")
os.environ.setdefault("BINANCE_TESTNET_API_KEY", "test-key")
os.environ.setdefault("BINANCE_TESTNET_API_SECRET", "test-secret")

from app.crypto.services.execution_service import ExecutionError, ExecutionService


def _make_proposal(
    status: str = "APPROVED",
    expires_at: datetime | None = None,
    stop_loss: float | None = 60000.0,
    take_profit: list | None = None,
    direction: str = "LONG",
    symbol: str = "BTCUSDT",
    position_size_usdt: float = 40.0,
) -> MagicMock:
    p = MagicMock()
    p.id = uuid.uuid4()
    p.status = status
    p.symbol = symbol
    p.direction = direction
    p.stop_loss = stop_loss
    p.take_profit = take_profit if take_profit is not None else [{"tp_level": 66000.0}]
    p.position_size_usdt = position_size_usdt
    p.expires_at = expires_at
    p.full_proposal_md = "test proposal"
    p.news_summary = "test news"
    p.agent_vote_summary = {}
    p.entry_plan = {"primary_entry": 63500.0}
    p.kill_switch_passed = True
    p.kill_switch_details = {}
    return p


def _make_db(proposal: MagicMock | None = None, dup_position: bool = False) -> AsyncMock:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=proposal)
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _patch_external(mock_adapter_cls: MagicMock, mock_ks_cls: MagicMock) -> None:
    mock_adapter = AsyncMock()
    mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
    mock_adapter.__aexit__ = AsyncMock(return_value=None)
    mock_adapter.get_exchange_info = AsyncMock(return_value={"symbols": []})
    mock_adapter_cls.return_value = mock_adapter

    ks_instance = MagicMock()
    ks_result = MagicMock()
    ks_result.passed = True
    ks_result.blocked_reasons = []
    ks_instance.check = AsyncMock(return_value=ks_result)
    mock_ks_cls.return_value = ks_instance


@pytest.mark.anyio
async def test_execute_rejects_when_not_approved() -> None:
    proposal = _make_proposal(status="PENDING_APPROVAL")
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with (
        patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockA,
        patch("app.crypto.services.execution_service.KillSwitch") as MockKS,
    ):
        _patch_external(MockA, MockKS)
        with pytest.raises(ExecutionError, match="check_1_approval"):
            await svc._run_pre_checks(proposal, uuid.uuid4())


@pytest.mark.anyio
async def test_execute_rejects_when_expired() -> None:
    proposal = _make_proposal(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with (
        patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockA,
        patch("app.crypto.services.execution_service.KillSwitch") as MockKS,
    ):
        _patch_external(MockA, MockKS)
        with pytest.raises(ExecutionError, match="check_2_expiry"):
            await svc._run_pre_checks(proposal, uuid.uuid4())


@pytest.mark.anyio
async def test_execute_rejects_without_stop_loss() -> None:
    proposal = _make_proposal(stop_loss=None)
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockAdapter:
        mock_adapter = AsyncMock()
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock(return_value=None)
        mock_adapter.get_exchange_info = AsyncMock(return_value={"symbols": []})
        MockAdapter.return_value = mock_adapter

        with patch("app.crypto.services.execution_service.KillSwitch") as MockKS:
            ks_instance = MagicMock()
            ks_result = MagicMock()
            ks_result.passed = True
            ks_result.blocked_reasons = []
            ks_instance.check = AsyncMock(return_value=ks_result)
            MockKS.return_value = ks_instance

            with pytest.raises(ExecutionError, match="check_9_sl"):
                await svc._run_pre_checks(proposal, uuid.uuid4())


@pytest.mark.anyio
async def test_execute_rejects_without_take_profit() -> None:
    proposal = _make_proposal(take_profit=[])
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockAdapter:
        mock_adapter = AsyncMock()
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock(return_value=None)
        mock_adapter.get_exchange_info = AsyncMock(return_value={"symbols": []})
        MockAdapter.return_value = mock_adapter

        with patch("app.crypto.services.execution_service.KillSwitch") as MockKS:
            ks_instance = MagicMock()
            ks_result = MagicMock()
            ks_result.passed = True
            ks_result.blocked_reasons = []
            ks_instance.check = AsyncMock(return_value=ks_result)
            MockKS.return_value = ks_instance

            with pytest.raises(ExecutionError, match="check_10_tp"):
                await svc._run_pre_checks(proposal, uuid.uuid4())


@pytest.mark.anyio
async def test_execute_rejects_when_kill_switch_blocks() -> None:
    proposal = _make_proposal()
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockAdapter:
        mock_adapter = AsyncMock()
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock(return_value=None)
        mock_adapter.get_exchange_info = AsyncMock(return_value={"symbols": []})
        MockAdapter.return_value = mock_adapter

        with patch("app.crypto.services.execution_service.KillSwitch") as MockKS:
            ks_instance = MagicMock()
            ks_result = MagicMock()
            ks_result.passed = False
            ks_result.blocked_reasons = ["max_daily_loss exceeded"]
            ks_instance.check = AsyncMock(return_value=ks_result)
            MockKS.return_value = ks_instance

            with pytest.raises(ExecutionError, match="check_12_kill_switch"):
                await svc._run_pre_checks(proposal, uuid.uuid4())


def test_extract_tp_levels_handles_dict_format() -> None:
    svc = ExecutionService.__new__(ExecutionService)
    levels = svc._extract_tp_levels(
        [
            {"tp_level": 66000.0},
            {"tp_level": 67000.0},
            {"price": 68000.0},
        ]
    )
    assert levels == [66000.0, 67000.0, 68000.0]


def test_extract_tp_levels_handles_flat_list() -> None:
    svc = ExecutionService.__new__(ExecutionService)
    levels = svc._extract_tp_levels([65000.0, 66000.0])
    assert levels == [65000.0, 66000.0]


def test_extract_tp_levels_returns_sorted() -> None:
    svc = ExecutionService.__new__(ExecutionService)
    levels = svc._extract_tp_levels([{"tp_level": 70000}, {"tp_level": 66000}])
    assert levels == [66000.0, 70000.0]


@pytest.mark.anyio
async def test_sl_placement_failure_blocks_and_flags_needs_attention() -> None:
    """C5 (paper): if the stop-loss order is rejected after the entry fills, the proposal is NOT
    marked EXECUTED — the position is flagged NEEDS_ATTENTION and a blocking ExecutionError is
    raised. Adapter is fully mocked, so no real/demo exchange order is placed."""
    proposal = _make_proposal()
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    # Adapter: entry order fills, but the exchange REJECTS the stop-loss order.
    adapter = AsyncMock()
    adapter.set_leverage = AsyncMock(return_value={})
    adapter.place_market_order = AsyncMock(return_value={"orderId": "E1", "avgPrice": "63500"})
    adapter.place_stop_market_order = AsyncMock(side_effect=RuntimeError("SL rejected"))
    adapter.place_take_profit_market_order = AsyncMock(return_value={"orderId": "T1"})
    adapter.get_exchange_info = AsyncMock(return_value={"symbols": []})

    # Validating the SL-failure branch, not sizing math — stub price/filters deterministically.
    svc._get_mark_price_safe = AsyncMock(return_value=63500.0)  # type: ignore[method-assign]
    svc._validate_symbol_filters = MagicMock(return_value=(0.001, []))  # type: ignore[method-assign]

    status_calls: list[str] = []

    async def record_status(_proposal: object, status: str) -> None:
        status_calls.append(status)

    svc._update_proposal_status = AsyncMock(side_effect=record_status)  # type: ignore[method-assign]

    with pytest.raises(ExecutionError, match="NEEDS_ATTENTION"):
        await svc._execute_proposal(adapter, proposal, uuid.uuid4(), uuid.uuid4())

    # The proposal is flagged NEEDS_ATTENTION and is NEVER marked EXECUTED.
    assert "NEEDS_ATTENTION" in status_calls
    assert "EXECUTED" not in status_calls
    # SL was attempted once; TP placement was never reached (we hard-blocked first).
    adapter.place_stop_market_order.assert_awaited_once()
    adapter.place_take_profit_market_order.assert_not_called()
    # The live-but-unprotected position is persisted as NEEDS_ATTENTION (not rolled back / hidden).
    positions = [c.args[0] for c in db.add.call_args_list if type(c.args[0]).__name__ == "Position"]
    assert positions and positions[-1].status == "NEEDS_ATTENTION"
    # The unprotected exposure is committed so it stays tracked.
    db.commit.assert_awaited()
    # Step-4 semantics: the TradeExecution row must NOT be SUCCESS — an entry that filled but
    # whose SL was rejected is ENTRY_FILLED_SL_FAILED (a non-complete, NEEDS_ATTENTION trade).
    executions = [
        c.args[0] for c in db.add.call_args_list if type(c.args[0]).__name__ == "TradeExecution"
    ]
    assert executions and executions[-1].execution_status == "ENTRY_FILLED_SL_FAILED"
    assert executions[-1].execution_status != "SUCCESS"


@pytest.mark.anyio
async def test_entry_and_sl_confirmed_marks_success_and_executed() -> None:
    """Happy path: entry fills AND the SL is confirmed → TradeExecution is SUCCESS and the
    proposal is marked EXECUTED. Adapter fully mocked — no real/demo order is placed."""
    proposal = _make_proposal(take_profit=[{"tp_level": 66000.0}])
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    adapter = AsyncMock()
    adapter.set_leverage = AsyncMock(return_value={})
    adapter.place_market_order = AsyncMock(return_value={"orderId": "E1", "avgPrice": "63500"})
    # SL/TP now return an `algoId` (mirrored to `orderId` by the adapter normalizer).
    adapter.place_stop_market_order = AsyncMock(
        return_value={"orderId": "ALGO-SL-1", "algoId": "ALGO-SL-1"}
    )
    adapter.place_take_profit_market_order = AsyncMock(
        return_value={"orderId": "ALGO-TP-1", "algoId": "ALGO-TP-1"}
    )
    adapter.get_exchange_info = AsyncMock(return_value={"symbols": []})

    svc._get_mark_price_safe = AsyncMock(return_value=63500.0)  # type: ignore[method-assign]
    svc._validate_symbol_filters = MagicMock(return_value=(0.001, []))  # type: ignore[method-assign]

    status_calls: list[str] = []

    async def record_status(_proposal: object, status: str) -> None:
        status_calls.append(status)

    svc._update_proposal_status = AsyncMock(side_effect=record_status)  # type: ignore[method-assign]

    with patch(
        "app.crypto.services.execution_service.build_trade_journal_raw_facts", return_value={}
    ):
        out = await svc._execute_proposal(adapter, proposal, uuid.uuid4(), uuid.uuid4())

    assert out["status"] == "SUCCESS"
    assert out["sl_order_id"] == "ALGO-SL-1"
    assert "EXECUTED" in status_calls
    assert "NEEDS_ATTENTION" not in status_calls
    adapter.place_stop_market_order.assert_awaited_once()
    adapter.place_take_profit_market_order.assert_awaited()
    executions = [
        c.args[0] for c in db.add.call_args_list if type(c.args[0]).__name__ == "TradeExecution"
    ]
    assert executions and executions[-1].execution_status == "SUCCESS"
    assert executions[-1].sl_order_id == "ALGO-SL-1"


@pytest.mark.anyio
async def test_replay_after_sl_failure_is_blocked_before_any_order() -> None:
    """Replay safety: after an SL failure the proposal is NEEDS_ATTENTION, so re-running
    execute() fails check_1_approval in pre-checks — no second entry order is ever attempted."""
    proposal = _make_proposal(status="NEEDS_ATTENTION")
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with (
        patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockA,
        patch("app.crypto.services.execution_service.KillSwitch") as MockKS,
    ):
        _patch_external(MockA, MockKS)
        with pytest.raises(ExecutionError, match="check_1_approval"):
            await svc._run_pre_checks(proposal, uuid.uuid4())


@pytest.mark.anyio
async def test_pre_checks_reject_paper_trading_mode() -> None:
    """PAPER is local-simulation-only — ExecutionService (a real-order path) must reject it."""
    proposal = _make_proposal()
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with (
        patch("app.crypto.services.execution_service._TRADING_MODE", "PAPER"),
        patch.dict(os.environ, {"TRADING_MODE": "PAPER", "EXCHANGE_MODE": "paper"}),
        patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockA,
        patch("app.crypto.services.execution_service.KillSwitch") as MockKS,
    ):
        _patch_external(MockA, MockKS)
        with pytest.raises(ExecutionError, match="check_3_mode"):
            await svc._run_pre_checks(proposal, uuid.uuid4())


@pytest.mark.anyio
async def test_pre_checks_accept_demo_trading_mode_at_mode_gate() -> None:
    """DEMO is order-capable — it must pass the mode gate (any later failure is unrelated)."""
    proposal = _make_proposal()
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with (
        patch("app.crypto.services.execution_service._TRADING_MODE", "DEMO"),
        patch.dict(os.environ, {"TRADING_MODE": "DEMO", "EXCHANGE_MODE": "demo"}),
        patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockA,
        patch("app.crypto.services.execution_service.KillSwitch") as MockKS,
    ):
        _patch_external(MockA, MockKS)
        try:
            await svc._run_pre_checks(proposal, uuid.uuid4())
        except ExecutionError as exc:
            # DEMO must NOT be rejected by the mode gate or the conflict guard.
            assert "check_3_mode" not in str(exc)
            assert "check_3b_mode_conflict" not in str(exc)


@pytest.mark.anyio
async def test_pre_checks_block_on_mode_conflict() -> None:
    """DEMO trading mode but a live exchange mode is a conflict → fail closed."""
    proposal = _make_proposal()
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with (
        patch("app.crypto.services.execution_service._TRADING_MODE", "DEMO"),
        patch.dict(os.environ, {"TRADING_MODE": "DEMO", "EXCHANGE_MODE": "live"}),
        patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockA,
        patch("app.crypto.services.execution_service.KillSwitch") as MockKS,
    ):
        _patch_external(MockA, MockKS)
        with pytest.raises(ExecutionError, match="check_3b_mode_conflict"):
            await svc._run_pre_checks(proposal, uuid.uuid4())
