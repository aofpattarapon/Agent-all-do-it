"""Tests for the read-only, fail-closed trading readiness evaluation."""

from __future__ import annotations

import json

import pytest

from app.services.trading_readiness import evaluate_trading_readiness


def _set_demo_futures_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_FUTURES_DEMO_API_KEY", "demo-key-value")
    monkeypatch.setenv("BINANCE_FUTURES_DEMO_API_SECRET", "demo-secret-value")


def _set_testnet_futures_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "testnet-key-value")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "testnet-secret-value")


def test_paper_is_not_order_capable_and_never_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_MODE", "paper")
    monkeypatch.setenv("TRADING_MODE", "PAPER")
    monkeypatch.setenv("MARKET_TYPE", "futures")

    result = evaluate_trading_readiness()
    assert result["is_paper"] is True
    assert result["is_order_capable"] is False
    assert result["will_send_exchange_order"] is False
    assert result["readiness"] == "ready"
    assert result["mode_conflict"] is False


def test_demo_configured_is_order_capable_and_will_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("TRADING_MODE", "DEMO")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    _set_demo_futures_creds(monkeypatch)

    result = evaluate_trading_readiness()
    assert result["is_demo"] is True
    assert result["is_order_capable"] is True
    assert result["credentials_configured"] is True
    assert result["will_send_exchange_order"] is True
    assert result["readiness"] == "ready"
    assert result["order_destination"] == "Binance Futures Demo"
    assert result["base_url_label"] == "demo-fapi.binance.com"
    assert result["credentials_source"] == "BINANCE_FUTURES_DEMO_*"


def test_testnet_configured_is_order_capable_and_will_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_MODE", "testnet")
    monkeypatch.setenv("TRADING_MODE", "TESTNET")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    _set_testnet_futures_creds(monkeypatch)

    result = evaluate_trading_readiness()
    assert result["is_testnet"] is True
    assert result["is_order_capable"] is True
    assert result["will_send_exchange_order"] is True
    assert result["readiness"] == "ready"


def test_live_is_fail_closed_without_explicit_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_MODE", "live")
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    monkeypatch.setenv("BINANCE_LIVE_API_KEY", "live-key-value")
    monkeypatch.setenv("BINANCE_LIVE_API_SECRET", "live-secret-value")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    monkeypatch.setenv("ALLOW_ORDER_EXECUTION", "true")

    result = evaluate_trading_readiness()
    assert result["is_live"] is True
    assert result["will_send_exchange_order"] is False
    assert result["readiness"] == "not_ready"
    assert any("LIVE_TRADING_ENABLED" in reason for reason in result["blocking_reasons"])


def test_live_with_explicit_flags_will_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_MODE", "live")
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    monkeypatch.setenv("BINANCE_LIVE_API_KEY", "live-key-value")
    monkeypatch.setenv("BINANCE_LIVE_API_SECRET", "live-secret-value")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("ALLOW_ORDER_EXECUTION", "true")

    result = evaluate_trading_readiness()
    assert result["will_send_exchange_order"] is True
    assert result["readiness"] == "ready"


def test_mode_conflict_returns_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    # PAPER must never drive an order-capable exchange mode (the Phase 2B boundary).
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("TRADING_MODE", "PAPER")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    _set_demo_futures_creds(monkeypatch)

    result = evaluate_trading_readiness()
    assert result["mode_conflict"] is True
    assert result["readiness"] == "conflict"
    assert result["will_send_exchange_order"] is False


def test_missing_credentials_returns_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("TRADING_MODE", "DEMO")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    monkeypatch.delenv("BINANCE_FUTURES_DEMO_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_FUTURES_DEMO_API_SECRET", raising=False)

    result = evaluate_trading_readiness()
    assert result["credentials_configured"] is False
    assert result["readiness"] == "not_ready"
    assert result["will_send_exchange_order"] is False


def test_no_secret_values_are_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_MODE", "demo")
    monkeypatch.setenv("TRADING_MODE", "DEMO")
    monkeypatch.setenv("MARKET_TYPE", "futures")
    monkeypatch.setenv("BINANCE_FUTURES_DEMO_API_KEY", "SUPER-SECRET-KEY-1234")
    monkeypatch.setenv("BINANCE_FUTURES_DEMO_API_SECRET", "SUPER-SECRET-SECRET-5678")

    result = evaluate_trading_readiness()
    assert result["credential_values_exposed"] is False
    serialized = json.dumps(result)
    assert "SUPER-SECRET-KEY-1234" not in serialized
    assert "SUPER-SECRET-SECRET-5678" not in serialized
    # Only the env var *pattern* is surfaced, never a value.
    assert result["credentials_source"] == "BINANCE_FUTURES_DEMO_*"
