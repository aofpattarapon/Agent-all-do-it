"""Tests for dual-demo exchange routing guards.

Covers all 10 required scenarios:
1.  Spot demo routes to Spot Demo API (demo-api.binance.com/api).
2.  Futures demo routes to demo-fapi.binance.com.
3.  Spot testnet routes to Spot Testnet API (testnet.binance.vision/api).
4.  Spot demo blocks when endpoint would be Spot testnet (misconfigured env).
5.  Spot testnet blocks when endpoint would be Spot demo (misconfigured env).
6.  Spot demo blocks when endpoint would be demo-fapi (misconfigured env).
7.  Futures demo blocks when endpoint would be Spot endpoint (misconfigured env).
5.  Spot BUY MARKET uses quoteOrderQty (not quantity).
6.  Futures BUY MARKET does NOT use quoteOrderQty.
7.  Demo mode never selects live API keys.
8.  Production endpoint is blocked when EXCHANGE_MODE=demo.
9.  Missing MARKET_TYPE blocks execution.
10. Proposal market_type mismatch in handoff contract blocks execution.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from app.services.exchange_routing import (
    _FUTURES_DEMO_BASE,
    _FUTURES_LIVE_BASE,
    _SPOT_DEMO_BASE,
    _SPOT_LIVE_BASE,
    _SPOT_TESTNET_BASE,
    ExchangeProfile,
    resolve_demo_credentials,
    resolve_exchange_profile,
    validate_demo_routing,
)
from app.services.handoff_contracts import CRYPTO_HANDOFF_CONTRACTS, validate_handoff

# ── Helpers ────────────────────────────────────────────────────────────────────


def _env(**kwargs: str) -> dict[str, str]:
    """Build a minimal env override dict."""
    return kwargs


# ── Test 1: Spot demo routes to Spot Demo API ──────────────────────────────────


def test_spot_demo_routes_to_spot_demo() -> None:
    with patch.dict(os.environ, _env(MARKET_TYPE="spot", EXCHANGE_MODE="demo")):
        profile = resolve_exchange_profile()
    assert profile.market_type == "spot"
    assert profile.is_spot is True
    assert profile.endpoint_base == _SPOT_DEMO_BASE
    assert "demo-api.binance.com" in profile.endpoint_base
    assert "demo-fapi" not in profile.endpoint_base


# ── Test 2: Futures demo routes to demo-fapi.binance.com ──────────────────────


def test_futures_demo_routes_to_demo_fapi() -> None:
    with patch.dict(os.environ, _env(MARKET_TYPE="futures", EXCHANGE_MODE="demo")):
        profile = resolve_exchange_profile()
    assert profile.market_type == "futures"
    assert profile.is_spot is False
    assert profile.endpoint_base == _FUTURES_DEMO_BASE
    assert "demo-fapi.binance.com" in profile.endpoint_base


# ── Test 3: Spot testnet routes to Spot Testnet API ────────────────────────────


def test_spot_testnet_routes_to_spot_testnet() -> None:
    with patch.dict(os.environ, _env(MARKET_TYPE="spot", EXCHANGE_MODE="testnet")):
        profile = resolve_exchange_profile()
    assert profile.market_type == "spot"
    assert profile.is_spot is True
    assert profile.endpoint_base == _SPOT_TESTNET_BASE
    assert "testnet.binance.vision" in profile.endpoint_base


# ── Test 4: Spot demo blocks if endpoint resolves to Spot testnet ──────────────


def test_spot_demo_blocks_when_endpoint_is_spot_testnet() -> None:
    bad_profile = ExchangeProfile(
        market_type="spot",
        exchange_mode="demo",
        endpoint_base=_SPOT_TESTNET_BASE,
        api_key_env="BINANCE_SPOT_DEMO_API_KEY",
        api_secret_env="BINANCE_SPOT_DEMO_API_SECRET",
        is_demo=True,
        is_spot=True,
    )
    with (
        patch.dict(os.environ, _env(MARKET_TYPE="spot", EXCHANGE_MODE="demo")),
        patch("app.services.exchange_routing.resolve_exchange_profile", return_value=bad_profile),
    ):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("spot demo routed to Spot Testnet endpoint" in e for e in result.errors)


# ── Test 5: Spot testnet blocks if endpoint resolves to Spot demo ──────────────


def test_spot_testnet_blocks_when_endpoint_is_spot_demo() -> None:
    bad_profile = ExchangeProfile(
        market_type="spot",
        exchange_mode="testnet",
        endpoint_base=_SPOT_DEMO_BASE,
        api_key_env="BINANCE_SPOT_TESTNET_API_KEY",
        api_secret_env="BINANCE_SPOT_TESTNET_API_SECRET",
        is_demo=True,
        is_spot=True,
    )
    with (
        patch.dict(os.environ, _env(MARKET_TYPE="spot", EXCHANGE_MODE="testnet")),
        patch("app.services.exchange_routing.resolve_exchange_profile", return_value=bad_profile),
    ):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("spot testnet routed to Spot Demo endpoint" in e for e in result.errors)


# ── Test 6: Spot demo blocks if endpoint resolves to demo-fapi ─────────────────


def test_spot_demo_blocks_when_endpoint_is_futures_demo() -> None:
    """Guard 2: spot market must not route to demo-fapi."""
    bad_profile = ExchangeProfile(
        market_type="spot",
        exchange_mode="demo",
        endpoint_base=_FUTURES_DEMO_BASE,  # WRONG endpoint for spot
        api_key_env="BINANCE_SPOT_DEMO_API_KEY",
        api_secret_env="BINANCE_SPOT_DEMO_API_SECRET",
        is_demo=True,
        is_spot=True,
    )
    with (
        patch.dict(os.environ, _env(MARKET_TYPE="spot", EXCHANGE_MODE="demo")),
        patch("app.services.exchange_routing.resolve_exchange_profile", return_value=bad_profile),
    ):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("spot market routed to futures endpoint" in e for e in result.errors)


# ── Test 7: Futures demo blocks if endpoint resolves to Spot endpoint ──────────


def test_futures_demo_blocks_when_endpoint_is_spot_testnet() -> None:
    """Guard 3: futures market must not route to spot endpoints."""
    bad_profile = ExchangeProfile(
        market_type="futures",
        exchange_mode="demo",
        endpoint_base=_SPOT_TESTNET_BASE,  # WRONG endpoint for futures
        api_key_env="BINANCE_FUTURES_DEMO_API_KEY",
        api_secret_env="BINANCE_FUTURES_DEMO_API_SECRET",
        is_demo=True,
        is_spot=False,
    )
    with (
        patch.dict(os.environ, _env(MARKET_TYPE="futures", EXCHANGE_MODE="demo")),
        patch("app.services.exchange_routing.resolve_exchange_profile", return_value=bad_profile),
    ):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("futures market routed to spot endpoint" in e for e in result.errors)


def test_futures_demo_blocks_when_endpoint_is_spot_demo() -> None:
    bad_profile = ExchangeProfile(
        market_type="futures",
        exchange_mode="demo",
        endpoint_base=_SPOT_DEMO_BASE,
        api_key_env="BINANCE_FUTURES_DEMO_API_KEY",
        api_secret_env="BINANCE_FUTURES_DEMO_API_SECRET",
        is_demo=True,
        is_spot=False,
    )
    with (
        patch.dict(os.environ, _env(MARKET_TYPE="futures", EXCHANGE_MODE="demo")),
        patch("app.services.exchange_routing.resolve_exchange_profile", return_value=bad_profile),
    ):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("futures market routed to spot endpoint" in e for e in result.errors)


# ── Test 5: Spot BUY MARKET uses quoteOrderQty ─────────────────────────────────


@pytest.mark.anyio
async def test_spot_buy_market_uses_quote_order_qty() -> None:
    """validate_order_request for spot BUY MARKET must NOT require quantity."""
    from app.agents.tools import exchange_tool as et

    with (
        patch.dict(os.environ, _env(MARKET_TYPE="spot", EXCHANGE_MODE="paper")),
        patch.object(et, "MARKET_TYPE", "spot"),
        patch.object(et, "EXCHANGE_MODE", "paper"),
    ):
        result = await et.validate_order_request(
            symbol="BTCUSDT",
            side="buy",
            amount=0.001,
            order_type="market",
            notional_usdt=65.0,  # quoteOrderQty path requires this
        )
    # Spot BUY MARKET is valid when notional_usdt is provided.
    assert result["passed"] is True
    assert result["market_type"] == "spot"


@pytest.mark.anyio
async def test_spot_buy_market_fails_without_notional() -> None:
    """Spot BUY MARKET without notional_usdt must fail (quoteOrderQty guard)."""
    from app.agents.tools import exchange_tool as et

    with patch.object(et, "MARKET_TYPE", "spot"), patch.object(et, "EXCHANGE_MODE", "paper"):
        result = await et.validate_order_request(
            symbol="BTCUSDT",
            side="buy",
            amount=0.001,
            order_type="market",
            notional_usdt=None,  # missing — should fail
        )
    assert result["passed"] is False
    assert any("quoteOrderQty" in e for e in result["errors"])


# ── Test 6: Futures BUY MARKET does NOT use quoteOrderQty ─────────────────────


@pytest.mark.anyio
async def test_futures_buy_market_does_not_require_quote_order_qty() -> None:
    """Futures BUY MARKET is valid without notional_usdt."""
    from app.agents.tools import exchange_tool as et

    with patch.object(et, "MARKET_TYPE", "futures"), patch.object(et, "EXCHANGE_MODE", "paper"):
        result = await et.validate_order_request(
            symbol="BTCUSDT",
            side="buy",
            amount=0.001,
            order_type="market",
            notional_usdt=None,  # not required for futures
        )
    assert result["passed"] is True
    assert result["market_type"] == "futures"


# ── Test 7: Demo mode never selects live API keys ──────────────────────────────


def test_demo_mode_never_uses_live_keys() -> None:
    """resolve_demo_credentials must not return the live key even if set."""
    live_key = "LIVE_KEY_SHOULD_NOT_APPEAR"
    with patch.dict(
        os.environ,
        {
            "MARKET_TYPE": "futures",
            "EXCHANGE_MODE": "demo",
            "BINANCE_LIVE_API_KEY": live_key,
            "BINANCE_FUTURES_DEMO_API_KEY": "demo_futures_key",
            "BINANCE_FUTURES_DEMO_API_SECRET": "demo_futures_secret",
        },
        clear=False,
    ):
        key, _ = resolve_demo_credentials("futures", "demo")
    assert key != live_key
    assert key == "demo_futures_key"


def test_spot_testnet_prefers_spot_testnet_keys() -> None:
    with patch.dict(
        os.environ,
        {
            "BINANCE_SPOT_TESTNET_API_KEY": "spot_testnet_key",
            "BINANCE_SPOT_TESTNET_API_SECRET": "spot_testnet_secret",
            "BINANCE_SPOT_DEMO_API_KEY": "spot_demo_key",
            "BINANCE_SPOT_DEMO_API_SECRET": "spot_demo_secret",
        },
        clear=False,
    ):
        key, secret = resolve_demo_credentials("spot", "testnet")
    assert key == "spot_testnet_key"
    assert secret == "spot_testnet_secret"


def test_demo_routing_blocks_when_resolved_key_matches_live_key() -> None:
    """Guard 4: if resolved demo key == live key, validate_demo_routing blocks."""
    shared_key = "same_key_for_both_demo_and_live"
    env = {
        "MARKET_TYPE": "futures",
        "EXCHANGE_MODE": "demo",
        "BINANCE_LIVE_API_KEY": shared_key,
        "BINANCE_FUTURES_DEMO_API_KEY": shared_key,  # same as live — must be blocked
        "BINANCE_FUTURES_DEMO_API_SECRET": "some_secret",
    }
    with patch.dict(os.environ, env, clear=False):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("BINANCE_LIVE_API_KEY" in e for e in result.errors)


# ── Test 8: Production endpoint blocked when EXCHANGE_MODE=demo ────────────────


def test_production_endpoint_blocked_in_demo_mode() -> None:
    """Guard 1: if a production endpoint sneaks in under demo mode, block it."""
    bad_profile = ExchangeProfile(
        market_type="futures",
        exchange_mode="demo",
        endpoint_base=_FUTURES_LIVE_BASE,  # production — must be blocked
        api_key_env="BINANCE_FUTURES_DEMO_API_KEY",
        api_secret_env="BINANCE_FUTURES_DEMO_API_SECRET",
        is_demo=True,
        is_spot=False,
    )
    with (
        patch.dict(os.environ, _env(MARKET_TYPE="futures", EXCHANGE_MODE="demo")),
        patch("app.services.exchange_routing.resolve_exchange_profile", return_value=bad_profile),
    ):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("production endpoint" in e for e in result.errors)


def test_spot_production_endpoint_blocked_in_demo_mode() -> None:
    """Spot production endpoint (api.binance.com) must also be blocked in demo."""
    bad_profile = ExchangeProfile(
        market_type="spot",
        exchange_mode="demo",
        endpoint_base=_SPOT_LIVE_BASE,  # production — must be blocked
        api_key_env="BINANCE_SPOT_DEMO_API_KEY",
        api_secret_env="BINANCE_SPOT_DEMO_API_SECRET",
        is_demo=True,
        is_spot=True,
    )
    with (
        patch.dict(os.environ, _env(MARKET_TYPE="spot", EXCHANGE_MODE="demo")),
        patch("app.services.exchange_routing.resolve_exchange_profile", return_value=bad_profile),
    ):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("production endpoint" in e for e in result.errors)


def test_live_mode_blocked_when_live_trading_disabled() -> None:
    with patch.dict(
        os.environ,
        {
            "MARKET_TYPE": "spot",
            "EXCHANGE_MODE": "live",
            "LIVE_TRADING_ENABLED": "false",
        },
        clear=False,
    ):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("LIVE_TRADING_ENABLED=false" in e for e in result.errors)


# ── Test 9: Missing MARKET_TYPE blocks execution ───────────────────────────────


def test_missing_market_type_blocks_routing() -> None:
    """validate_demo_routing must return passed=False when MARKET_TYPE is absent."""
    env = {k: v for k, v in os.environ.items() if k != "MARKET_TYPE"}
    env["EXCHANGE_MODE"] = "demo"
    with patch.dict(os.environ, env, clear=True):
        result = validate_demo_routing()
    assert result.passed is False
    assert any("MARKET_TYPE" in e for e in result.errors)


def test_unknown_market_type_raises_on_resolve() -> None:
    """resolve_exchange_profile raises ValueError for unknown MARKET_TYPE values."""
    with (
        patch.dict(os.environ, {"MARKET_TYPE": "perpetual_swap", "EXCHANGE_MODE": "demo"}),
        pytest.raises(ValueError, match="Unknown MARKET_TYPE"),
    ):
        resolve_exchange_profile()


# ── Test 10: Proposal market_type mismatch blocks handoff contract ─────────────


def test_proposal_without_market_type_fails_handoff_contract() -> None:
    """trade_proposal_to_gate_or_execute contract requires market_type."""
    contract = next(
        c for c in CRYPTO_HANDOFF_CONTRACTS if c.name == "trade_proposal_to_gate_or_execute"
    )
    # Proposal missing market_type field.
    proposal_missing_market_type = json.dumps(
        {
            "approval_status": "APPROVED",
            "direction": "LONG",
            "entry_plan": {"primary_entry": 65000.0},
            "stop_loss": 63000.0,
            "take_profit": [66000.0, 67000.0],
            "risk_reward": 2.5,
            "position_size_usdt": 50.0,
            # market_type intentionally absent
        }
    )
    result = validate_handoff(proposal_missing_market_type, contract)
    assert result.passed is False
    assert "market_type" in result.missing_fields


def test_proposal_with_market_type_passes_handoff_contract() -> None:
    """trade_proposal_to_gate_or_execute contract passes when market_type is present."""
    contract = next(
        c for c in CRYPTO_HANDOFF_CONTRACTS if c.name == "trade_proposal_to_gate_or_execute"
    )
    proposal_with_market_type = json.dumps(
        {
            "approval_status": "APPROVED",
            "direction": "LONG",
            "entry_plan": {"primary_entry": 65000.0},
            "stop_loss": 63000.0,
            "take_profit": [66000.0, 67000.0],
            "risk_reward": 2.5,
            "position_size_usdt": 50.0,
            "market_type": "futures",
        }
    )
    result = validate_handoff(proposal_with_market_type, contract)
    assert result.passed is True
    assert result.missing_fields == ()
