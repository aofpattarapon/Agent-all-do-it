"""Unit tests for the read-only execution-visibility normalization layer.

These cover mode normalization (the misleading-PAPER fix), protection classification
(ACTIVE / PARTIAL / MISSING / CLOSED / UNKNOWN), and the canonical ETHUSDT demo-futures
verification case from run 29473a8a-89be-477f-96c2-7d530b42eb9b.
"""

from app.services.execution_visibility import (
    build_execution_visibility,
    build_protection,
    build_protection_summary,
)

# Canonical ETHUSDT SHORT demo-futures fixture (run 29473a8a-…).
_ETH_KWARGS = {
    "exchange": "binance_demo_futures",
    "raw_response": {"mode": "DEMO_FUTURES", "exchange": "binance_demo_futures"},
    "sl_order_id": "1000000104692896",
    "tp_order_ids": ["9690349120", "9690349355", "9690349529"],
    "stop_loss": 1724.95,
    "take_profits": [1574.95, 1524.95, 1474.95],
    "position_status": "OPEN",
}


def test_demo_futures_mode_is_not_labelled_paper():
    """A demo-futures execution must surface as DEMO_FUTURES, submitted, non-real-money."""
    v = build_execution_visibility(**_ETH_KWARGS)
    assert v["execution_mode_label"] == "DEMO_FUTURES"
    assert v["safety_mode"] == "DEMO"
    assert v["submitted_to_exchange"] is True
    assert v["simulated_only"] is False
    assert v["real_money"] is False
    assert v["exchange_route"] == "binance_demo_futures"


def test_eth_run_protection_is_active_with_all_orders():
    """The ETHUSDT run has SL + 3 TP reduce-only orders → ACTIVE via separate orders."""
    v = build_execution_visibility(**_ETH_KWARGS)
    p = v["protection"]
    assert p["status"] == "ACTIVE"
    assert p["source"] == "separate_reduce_only_orders"
    assert p["stop_loss"] == {"price": 1724.95, "order_id": "1000000104692896", "status": "OPEN"}
    assert [tp["order_id"] for tp in p["take_profits"]] == [
        "9690349120",
        "9690349355",
        "9690349529",
    ]
    assert [tp["price"] for tp in p["take_profits"]] == [1574.95, 1524.95, 1474.95]
    assert [tp["level"] for tp in p["take_profits"]] == [1, 2, 3]


def test_paper_mode_is_simulated_only():
    """Pure paper executions are simulated, not submitted to any exchange."""
    v = build_execution_visibility(
        exchange="paper_trade",
        raw_response={"mode": "PAPER"},
        sl_order_id="PAPER-SL-1",
        tp_order_ids=["PAPER-TP1-1"],
        stop_loss=100.0,
        take_profits=[110.0],
        position_status="OPEN",
    )
    assert v["execution_mode_label"] == "PAPER_SIMULATION"
    assert v["simulated_only"] is True
    assert v["submitted_to_exchange"] is False
    assert v["real_money"] is False
    # Simulated protection still classifies as ACTIVE but source reflects simulation.
    assert v["protection"]["status"] == "ACTIVE"
    assert v["protection"]["source"] == "simulated"


def test_live_mode_is_real_money():
    v = build_execution_visibility(
        exchange="binance_live",
        raw_response={"mode": "LIVE"},
        sl_order_id="111",
        tp_order_ids=["222"],
        stop_loss=100.0,
        take_profits=[110.0],
        position_status="OPEN",
    )
    assert v["execution_mode_label"] == "LIVE"
    assert v["real_money"] is True
    assert v["submitted_to_exchange"] is True


def test_mode_falls_back_to_exchange_when_raw_missing():
    """Missing raw_response['mode'] still resolves via the exchange string."""
    v = build_execution_visibility(
        exchange="binance_demo_futures",
        raw_response={},
        sl_order_id="1",
        tp_order_ids=["2"],
        stop_loss=100.0,
        take_profits=[110.0],
        position_status="OPEN",
    )
    assert v["execution_mode_label"] == "DEMO_FUTURES"


def test_protection_partial_when_only_stop_loss():
    p = build_protection(
        sl_order_id="sl-1",
        tp_order_ids=[],
        stop_loss=100.0,
        take_profits=[],
        position_status="OPEN",
        submitted_to_exchange=True,
    )
    assert p["status"] == "PARTIAL"
    assert p["stop_loss"] is not None
    assert p["take_profits"] == []


def test_protection_partial_when_only_take_profit():
    p = build_protection(
        sl_order_id=None,
        tp_order_ids=["tp-1"],
        stop_loss=None,
        take_profits=[110.0],
        position_status="OPEN",
        submitted_to_exchange=True,
    )
    assert p["status"] == "PARTIAL"


def test_protection_missing_when_open_with_no_orders():
    p = build_protection(
        sl_order_id=None,
        tp_order_ids=[],
        stop_loss=None,
        take_profits=[],
        position_status="OPEN",
        submitted_to_exchange=True,
    )
    assert p["status"] == "MISSING"


def test_protection_closed_when_position_closed():
    v = build_execution_visibility(**{**_ETH_KWARGS, "position_status": "CLOSED"})
    p = v["protection"]
    assert p["status"] == "CLOSED"
    # Rows still render but marked closed; nothing is counted as active.
    assert p["sl_active"] is False
    assert p["tp_active_count"] == 0
    assert p["stop_loss"]["status"] == "CLOSED"


def test_protection_unknown_without_execution_data():
    """No execution record + unknown status → UNKNOWN, not a false MISSING."""
    v = build_execution_visibility(
        exchange=None,
        raw_response=None,
        sl_order_id=None,
        tp_order_ids=None,
        stop_loss=None,
        take_profits=None,
        position_status=None,
    )
    assert v["execution_mode_label"] == "UNKNOWN"
    assert v["protection"]["status"] == "UNKNOWN"


def test_take_profit_dict_shaped_prices_are_extracted():
    """TP levels may be stored as dicts; price extraction must handle that."""
    p = build_protection(
        sl_order_id="sl",
        tp_order_ids=["a", "b"],
        stop_loss=100.0,
        take_profits=[{"tp_level": 110.0}, {"price": 120.0}],
        position_status="OPEN",
        submitted_to_exchange=True,
    )
    assert [tp["price"] for tp in p["take_profits"]] == [110.0, 120.0]


def test_protection_summary_is_compact():
    s = build_protection_summary(
        sl_order_id="1000000104692896",
        tp_order_ids=["9690349120", "9690349355", "9690349529"],
        stop_loss=1724.95,
        take_profits=[1574.95, 1524.95, 1474.95],
        position_status="OPEN",
        submitted_to_exchange=True,
    )
    assert s["status"] == "ACTIVE"
    assert s["sl_active"] is True
    assert s["tp_active_count"] == 3
    assert s["tp_total_count"] == 3
    assert "separate reduce-only orders" in s["explanation"]
