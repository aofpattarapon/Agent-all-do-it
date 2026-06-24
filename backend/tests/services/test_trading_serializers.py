"""Unit tests for the read-only trading serializers (mode + confirmation enrichment).

These exercise ``_position_to_dict`` / ``_journal_to_dict`` directly with lightweight
attribute objects so no ORM/DB is needed. They lock in that the positions payload exposes
exchange-backed demo visibility and honest confirmation flags.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.api.routes.v1.trading import _journal_to_dict, _position_to_dict
from app.services.execution_visibility import build_trade_confirmation

_NOW = datetime(2026, 6, 15, tzinfo=UTC)


def _demo_execution(**overrides):
    base = {
        "id": uuid4(),
        "exchange": "binance_demo_futures",
        "order_id": "9753057980",
        "raw_response": {"mode": "DEMO_FUTURES", "exchange": "binance_demo_futures"},
        "sl_order_id": "1000000104692896",
        "tp_order_ids": ["9690349120"],
        "execution_status": "SUCCESS",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _position(**overrides):
    base = {
        "id": uuid4(),
        "execution_id": uuid4(),
        "symbol": "ETHUSDT",
        "side": "SHORT",
        "entry_price": 1700.0,
        "current_price": 1690.0,
        "size": 0.1,
        "stop_loss": 1724.95,
        "take_profits": [1574.95],
        "unrealized_pnl": None,
        "unrealized_pnl_pct": None,
        "status": "OPEN",
        "closed_at": None,
        "close_price": None,
        "realized_pnl": None,
        "close_reason": None,
        "created_at": _NOW,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_positions_expose_exchange_backed_demo_visibility():
    """An open demo-futures position surfaces DEMO_FUTURES visibility, not paper."""
    pos = _position()
    d = _position_to_dict(pos, _demo_execution())
    assert d["execution_visibility"]["execution_mode_label"] == "DEMO_FUTURES"
    assert d["execution_visibility"]["submitted_to_exchange"] is True
    assert d["execution_visibility"]["simulated_only"] is False
    assert d["order_placed"] is True
    assert d["position_created"] is True


def test_monitor_closed_position_exposes_exchange_confirmed_and_real_pnl():
    """A monitor-closed demo position is exchange-confirmed with a booked (non-estimated) PnL."""
    pos = _position(
        status="CLOSED",
        closed_at=_NOW,
        close_price=1680.0,
        realized_pnl=-0.10752,
        close_reason="UNKNOWN_EXCHANGE_FLAT",
    )
    d = _position_to_dict(pos, _demo_execution())
    assert d["exchange_confirmed"] is True
    assert d["pnl_estimated"] is False
    assert d["close_reason"] == "UNKNOWN_EXCHANGE_FLAT"


def test_paper_position_is_not_exchange_confirmed():
    """A closed paper-simulation position is never exchange-confirmed."""
    pos = _position(status="CLOSED", realized_pnl=5.0, close_reason="TP")
    paper_exec = _demo_execution(
        exchange="paper_trade",
        raw_response={"mode": "PAPER", "exchange": "paper_trade"},
        order_id="PAPER-7FB3891F",
    )
    d = _position_to_dict(pos, paper_exec)
    assert d["execution_visibility"]["execution_mode_label"] == "PAPER_SIMULATION"
    assert d["exchange_confirmed"] is False
    assert d["pnl_estimated"] is False  # realized PnL booked even in simulation


def test_open_position_pnl_is_estimated():
    """An open position has no booked realized PnL → pnl_estimated True, not exchange_confirmed."""
    d = _position_to_dict(_position(), _demo_execution())
    assert d["pnl_estimated"] is True
    assert d["exchange_confirmed"] is False


def test_position_without_execution_reports_no_order():
    """A position whose execution row is missing reports order_placed False, mode UNKNOWN."""
    d = _position_to_dict(_position(), None)
    assert d["order_placed"] is False
    assert d["execution_visibility"]["execution_mode_label"] == "UNKNOWN"


def test_journal_pnl_estimated_flag():
    journal = SimpleNamespace(
        id=uuid4(),
        position_id=uuid4(),
        symbol="ETHUSDT",
        direction="SHORT",
        entry_price=1700.0,
        exit_price=1680.0,
        size=0.1,
        realized_pnl=-0.10752,
        realized_pnl_pct=-0.6,
        holding_time_minutes=42,
        result="LOSS",
        original_thesis=None,
        what_happened=None,
        mistakes=None,
        what_worked=None,
        improvement=None,
        post_review_md=None,
        decision_log=[],
        news_used=[],
        agent_votes={},
        created_at=_NOW,
    )
    assert _journal_to_dict(journal)["pnl_estimated"] is False
    journal.realized_pnl = None
    assert _journal_to_dict(journal)["pnl_estimated"] is True


def test_build_trade_confirmation_order_placed_requires_execution():
    c = build_trade_confirmation(
        position_status="OPEN",
        realized_pnl=None,
        submitted_to_exchange=True,
        has_execution=False,
        order_id=None,
        execution_status=None,
    )
    assert c["order_placed"] is False
    assert c["position_created"] is True
