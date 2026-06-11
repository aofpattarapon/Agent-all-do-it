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

from app.crypto.services.execution_service import ExecutionError, ExecutionService  # noqa: E402


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

    with patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockA, \
         patch("app.crypto.services.execution_service.KillSwitch") as MockKS:
        _patch_external(MockA, MockKS)
        with pytest.raises(ExecutionError, match="check_1_approval"):
            await svc._run_pre_checks(proposal, uuid.uuid4())


@pytest.mark.anyio
async def test_execute_rejects_when_expired() -> None:
    proposal = _make_proposal(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    db = _make_db(proposal=proposal)
    svc = ExecutionService(db)

    with patch("app.crypto.services.execution_service.BinanceFuturesAdapter") as MockA, \
         patch("app.crypto.services.execution_service.KillSwitch") as MockKS:
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
    levels = svc._extract_tp_levels([
        {"tp_level": 66000.0},
        {"tp_level": 67000.0},
        {"price": 68000.0},
    ])
    assert levels == [66000.0, 67000.0, 68000.0]


def test_extract_tp_levels_handles_flat_list() -> None:
    svc = ExecutionService.__new__(ExecutionService)
    levels = svc._extract_tp_levels([65000.0, 66000.0])
    assert levels == [65000.0, 66000.0]


def test_extract_tp_levels_returns_sorted() -> None:
    svc = ExecutionService.__new__(ExecutionService)
    levels = svc._extract_tp_levels([{"tp_level": 70000}, {"tp_level": 66000}])
    assert levels == [66000.0, 70000.0]
