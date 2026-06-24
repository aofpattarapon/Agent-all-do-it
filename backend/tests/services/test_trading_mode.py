"""Unit tests for the authoritative trading-mode resolution and runtime visibility.

These cover ``build_runtime_visibility`` — the single source of truth for the UI-facing
runtime mode object — across the paper / demo / testnet / live configurations, driven
entirely by environment variables (the same vars the execution path reads).
"""

import pytest

from app.services import trading_mode
from app.services.trading_mode import (
    build_runtime_visibility,
    delete_trading_mode_overrides,
    resolve_trading_mode,
    validate_trading_mode_pair,
    write_trading_mode_overrides,
)


def _set_env(monkeypatch, **env: str) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_demo_futures_returns_exchange_demo(monkeypatch):
    """First-class DEMO: EXCHANGE_MODE=demo + TRADING_MODE=DEMO, futures, live disabled."""
    _set_env(
        monkeypatch,
        EXCHANGE_MODE="demo",
        TRADING_MODE="DEMO",
        MARKET_TYPE="futures",
        EXCHANGE="BINANCE_FUTURES",
        LIVE_TRADING_ENABLED="false",
        ALLOW_ORDER_EXECUTION="true",
    )
    v = build_runtime_visibility()
    assert v["runtime_mode"] == "exchange_demo"
    assert v["label"] == "Binance Demo Futures"
    assert v["is_exchange_backed"] is True
    assert v["is_paper_simulation"] is False
    assert v["is_local_simulation"] is False
    assert v["is_order_capable"] is True
    assert v["is_demo"] is True
    assert v["is_testnet"] is False
    assert v["is_live"] is False
    assert v["order_placement_enabled"] is False
    assert v["monitoring_exchange_backed"] is True
    assert v["safety_label"] == "Virtual money / no live funds"
    assert v["market_type"] == "futures"
    assert v["exchange"] == "binance"
    assert v["exchange_environment"] == "demo"
    assert v["trading_mode"] == "DEMO"
    assert v["conflict"] is None


def test_paper_plus_demo_is_flagged_as_conflict(monkeypatch):
    """The previously-dangerous mixed mode is now a visible conflict, not paper-safe."""
    _set_env(
        monkeypatch,
        EXCHANGE_MODE="demo",
        TRADING_MODE="PAPER",
        MARKET_TYPE="futures",
        LIVE_TRADING_ENABLED="false",
        ALLOW_ORDER_EXECUTION="true",
    )
    v = build_runtime_visibility()
    assert v["conflict"] is not None
    assert "PAPER" in v["conflict"]


def test_paper_returns_paper_simulation(monkeypatch):
    _set_env(
        monkeypatch,
        EXCHANGE_MODE="paper",
        TRADING_MODE="PAPER",
        MARKET_TYPE="futures",
        LIVE_TRADING_ENABLED="false",
        ALLOW_ORDER_EXECUTION="true",
    )
    v = build_runtime_visibility()
    assert v["runtime_mode"] == "paper_simulation"
    assert v["label"] == "Paper Simulation"
    assert v["is_exchange_backed"] is False
    assert v["is_paper_simulation"] is True
    assert v["is_live"] is False
    assert v["monitoring_exchange_backed"] is False
    assert v["order_placement_enabled"] is False
    assert v["safety_label"] == "Simulated / no orders placed"


def test_testnet_returns_exchange_testnet(monkeypatch):
    _set_env(
        monkeypatch,
        EXCHANGE_MODE="testnet",
        TRADING_MODE="TESTNET",
        MARKET_TYPE="futures",
        LIVE_TRADING_ENABLED="false",
        ALLOW_ORDER_EXECUTION="true",
    )
    v = build_runtime_visibility()
    assert v["runtime_mode"] == "exchange_testnet"
    assert v["label"] == "Binance Testnet Futures"
    assert v["is_exchange_backed"] is True
    assert v["is_paper_simulation"] is False
    assert v["is_live"] is False
    assert v["monitoring_exchange_backed"] is True
    assert v["order_placement_enabled"] is False
    assert v["safety_label"] == "Virtual money / no live funds"
    assert v["exchange_environment"] == "testnet"


def test_live_with_live_trading_enabled_returns_live(monkeypatch):
    _set_env(
        monkeypatch,
        EXCHANGE_MODE="live",
        TRADING_MODE="LIVE",
        MARKET_TYPE="futures",
        LIVE_TRADING_ENABLED="true",
        ALLOW_ORDER_EXECUTION="true",
    )
    v = build_runtime_visibility()
    assert v["runtime_mode"] == "live"
    assert v["label"] == "Binance Live Futures"
    assert v["is_exchange_backed"] is True
    assert v["is_paper_simulation"] is False
    assert v["is_live"] is True
    assert v["monitoring_exchange_backed"] is True
    assert v["order_placement_enabled"] is True
    assert v["safety_label"] == "REAL money / live funds at risk"


def test_live_without_live_trading_enabled_disables_order_placement(monkeypatch):
    """Live exchange mode but the live-trading flag is off → order placement stays disabled."""
    _set_env(
        monkeypatch,
        EXCHANGE_MODE="live",
        TRADING_MODE="LIVE",
        MARKET_TYPE="futures",
        LIVE_TRADING_ENABLED="false",
        ALLOW_ORDER_EXECUTION="true",
    )
    v = build_runtime_visibility()
    assert v["runtime_mode"] == "live"
    assert v["is_live"] is True
    assert v["order_placement_enabled"] is False


def test_demo_spot_label(monkeypatch):
    _set_env(
        monkeypatch,
        EXCHANGE_MODE="demo",
        TRADING_MODE="DEMO",
        MARKET_TYPE="spot",
        EXCHANGE="BINANCE_SPOT",
        LIVE_TRADING_ENABLED="false",
        ALLOW_ORDER_EXECUTION="true",
    )
    v = build_runtime_visibility()
    assert v["runtime_mode"] == "exchange_demo"
    assert v["label"] == "Binance Demo Spot"
    assert v["market_type"] == "spot"
    assert v["conflict"] is None


@pytest.mark.parametrize(
    "exchange_mode,expected_runtime",
    [
        ("paper", "paper_simulation"),
        ("demo", "exchange_demo"),
        ("testnet", "exchange_testnet"),
        ("live", "live"),
    ],
)
def test_runtime_mode_mapping(monkeypatch, exchange_mode, expected_runtime):
    # Each exchange_mode pairs 1:1 with its matching TRADING_MODE (no conflict).
    trading_mode = {
        "paper": "PAPER",
        "demo": "DEMO",
        "testnet": "TESTNET",
        "live": "LIVE",
    }[exchange_mode]
    _set_env(
        monkeypatch,
        EXCHANGE_MODE=exchange_mode,
        TRADING_MODE=trading_mode,
        MARKET_TYPE="futures",
        LIVE_TRADING_ENABLED="true" if exchange_mode == "live" else "false",
        ALLOW_ORDER_EXECUTION="true",
    )
    v = build_runtime_visibility()
    assert v["runtime_mode"] == expected_runtime
    assert v["conflict"] is None
    assert v["source"] == "environment"


def test_resolve_trading_mode_uses_redis_overrides(monkeypatch):
    """When Redis has overrides, they take precedence over environment variables."""
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("TRADING_MODE", "PAPER")
    monkeypatch.setattr(
        trading_mode,
        "_read_redis_mode_overrides",
        lambda: ("DEMO", "demo"),
    )
    status = resolve_trading_mode()
    assert status.trading_mode == "DEMO"
    assert status.exchange_mode == "demo"
    assert status.source == "runtime"
    assert status.conflict is None


def test_resolve_trading_mode_falls_back_to_env_when_redis_empty(monkeypatch):
    """Empty Redis overrides result in env-based resolution."""
    monkeypatch.setenv("EXCHANGE_MODE", "paper")
    monkeypatch.setenv("TRADING_MODE", "PAPER")
    monkeypatch.setattr(
        trading_mode,
        "_read_redis_mode_overrides",
        lambda: (None, None),
    )
    status = resolve_trading_mode()
    assert status.trading_mode == "PAPER"
    assert status.exchange_mode == "paper"
    assert status.source == "environment"


def test_validate_trading_mode_pair_rejects_conflict():
    with pytest.raises(ValueError, match="TRADING_MODE=PAPER"):
        validate_trading_mode_pair("PAPER", "demo")


def test_validate_trading_mode_pair_accepts_valid_pairs():
    validate_trading_mode_pair("PAPER", "paper")
    validate_trading_mode_pair("DEMO", "demo")
    validate_trading_mode_pair("TESTNET", "testnet")
    validate_trading_mode_pair("LIVE", "live")


def test_write_trading_mode_overrides_sets_redis_keys(monkeypatch):
    """Writing overrides stores normalized keys in Redis."""
    stored: dict[str, str] = {}

    class FakeRedis:
        def mget(self, keys: list[str]) -> list[str | None]:
            return [stored.get(k) for k in keys]

        def set(self, key: str, value: str) -> None:
            stored[key] = value

        def delete(self, *keys: str) -> int:
            for key in keys:
                stored.pop(key, None)
            return len(keys)

    monkeypatch.setattr(trading_mode, "_redis_sync_client", FakeRedis())
    write_trading_mode_overrides("TESTNET", "testnet")
    assert stored["trading:trading_mode"] == "TESTNET"
    assert stored["trading:exchange_mode"] == "testnet"

    # Updating should replace the previous values.
    write_trading_mode_overrides("live", "live")
    assert stored["trading:trading_mode"] == "LIVE"
    assert stored["trading:exchange_mode"] == "live"


def test_delete_trading_mode_overrides_clears_redis_keys(monkeypatch):
    stored: dict[str, str] = {
        "trading:trading_mode": "DEMO",
        "trading:exchange_mode": "demo",
    }

    class FakeRedis:
        def delete(self, *keys: str) -> int:
            removed = 0
            for key in keys:
                if key in stored:
                    del stored[key]
                    removed += 1
            return removed

    monkeypatch.setattr(trading_mode, "_redis_sync_client", FakeRedis())
    delete_trading_mode_overrides()
    assert "trading:trading_mode" not in stored
    assert "trading:exchange_mode" not in stored
