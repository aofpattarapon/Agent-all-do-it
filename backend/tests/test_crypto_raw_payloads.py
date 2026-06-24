from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.models.crypto_trading import CryptoRawPayload, TradeProposal
from app.services.crypto_persistence import CryptoPersistenceService, build_trade_journal_raw_facts


@pytest.mark.anyio
async def test_store_raw_payload_adds_record() -> None:
    db = SimpleNamespace(add=MagicMock(), flush=AsyncMock())
    svc = CryptoPersistenceService(db)

    record = await svc.store_raw_payload(
        project_id=uuid4(),
        run_id=uuid4(),
        payload_kind="market_data",
        agent_role="market_data",
        step_key="fetch_market_data",
        payload={"symbol": "BTCUSDT", "price": 100000.0},
    )

    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert isinstance(added, CryptoRawPayload)
    assert added.payload_kind == "market_data"
    assert added.agent_role == "market_data"
    assert added.step_key == "fetch_market_data"
    assert added.payload_json["symbol"] == "BTCUSDT"
    assert record is added
    db.flush.assert_awaited_once()


def test_build_trade_journal_raw_facts_keeps_structured_inputs() -> None:
    proposal = TradeProposal(
        id=uuid4(),
        project_id=uuid4(),
        run_id=uuid4(),
        symbol="BTCUSDT",
        direction="LONG",
        entry_plan={"primary_entry": 101000.0},
        take_profit=[{"tp_level": 103000.0}],
        stop_loss=99500.0,
        position_size_usdt=40.0,
        full_proposal_md="BTC breakout",
        news_summary="ETF support",
        agent_vote_summary={"majority_direction": "BULLISH"},
        raw_payload={
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_plan": {"primary_entry": 101000.0},
        },
    )

    facts = build_trade_journal_raw_facts(
        proposal=proposal,
        execution_payload={
            "execution_status": "SUCCESS",
            "order_id": "abc123",
            "sl_warning": "SL order failed: timeout",
        },
        position_id=uuid4(),
        journal_action="executed",
        entry_price=101050.0,
        size=0.0004,
    )

    assert facts["proposal"]["raw_payload"]["symbol"] == "BTCUSDT"
    assert facts["execution"]["order_id"] == "abc123"
    assert facts["execution"]["sl_warning"] == "SL order failed: timeout"
    assert facts["journal_action"] == "executed"


@pytest.mark.anyio
async def test_save_trade_proposal_sets_raw_payload() -> None:
    db = SimpleNamespace(add=MagicMock(), flush=AsyncMock())
    svc = CryptoPersistenceService(db)
    svc._latest_market_snapshot = AsyncMock(return_value=SimpleNamespace(market_regime="RISK_ON"))  # type: ignore[method-assign]
    svc._latest_trade_proposal = AsyncMock(return_value=None)  # type: ignore[method-assign]
    svc._count_hawk_votes = AsyncMock(return_value=3)  # type: ignore[method-assign]
    svc._news_events_for_run = AsyncMock(return_value=[])  # type: ignore[method-assign]

    payload = {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "strategy_type": "BREAKOUT",
        "time_horizon": "SWING",
        "entry_plan": {
            "primary_entry": 100.0,
            "entry_zone_low": 99.0,
            "entry_zone_high": 101.0,
        },
        "take_profit": [
            {"tp_level": 120.0, "rr_ratio": 2.0, "size_pct": 50},
            {"tp_level": 130.0, "rr_ratio": 3.0, "size_pct": 50},
        ],
        "stop_loss": 90.0,
        "risk_reward": 2.0,
        "position_size_usdt": 50.0,
        "total_score": 81.5,
        "sage_approved": True,
        "agent_vote_summary": {"majority_direction": "BULLISH"},
        "news_summary": "ETF optimism remains supportive.",
        "full_proposal_md": "BTC long setup",
    }

    with patch("app.services.crypto_persistence.KillSwitch") as kill_switch_cls:
        kill_switch_cls.return_value.check = AsyncMock(
            return_value=SimpleNamespace(
                passed=True,
                blocked_reasons=[],
                warnings=[],
                checks_run=["regime", "size"],
                adjusted_position_size_usdt=None,
            )
        )
        proposal = await svc.save_trade_proposal(
            project_id=uuid4(),
            run_id=uuid4(),
            payload=payload,
        )

    assert proposal is not None
    assert proposal.raw_payload == payload
    added = db.add.call_args_list[0].args[0]
    assert isinstance(added, TradeProposal)
    assert added.raw_payload == payload
