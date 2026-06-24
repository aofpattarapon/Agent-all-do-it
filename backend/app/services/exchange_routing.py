"""Exchange routing guards for explicit spot/futures demo/testnet/live support."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Canonical endpoint constants — never send demo/testnet traffic here.
_SPOT_LIVE_BASE = "https://api.binance.com/api"
_FUTURES_LIVE_BASE = "https://fapi.binance.com"
_PRODUCTION_ENDPOINTS: frozenset[str] = frozenset({_SPOT_LIVE_BASE, _FUTURES_LIVE_BASE})

# Demo/testnet endpoints.
_SPOT_DEMO_BASE = "https://demo-api.binance.com/api"
_SPOT_TESTNET_BASE = "https://testnet.binance.vision/api"
_FUTURES_DEMO_BASE = "https://demo-fapi.binance.com"

# Accepted MARKET_TYPE values and their normalization.
_MARKET_TYPE_ALIASES: dict[str, str] = {
    "spot": "spot",
    "futures": "futures",
    "usdm_futures": "futures",
    "usdm": "futures",
}


@dataclass(frozen=True)
class ExchangeProfile:
    """Resolved routing profile for the current env configuration."""

    market_type: str  # "spot" or "futures"
    exchange_mode: str  # "demo", "testnet", "paper", "live"
    endpoint_base: str  # REST base URL (empty for paper)
    api_key_env: str  # env var name that holds the API key
    api_secret_env: str  # env var name that holds the API secret
    is_demo: bool  # True for demo or testnet
    is_spot: bool  # True when market_type == "spot"


@dataclass
class RoutingValidation:
    """Result of validate_demo_routing()."""

    passed: bool
    profile: ExchangeProfile | None
    errors: list[str] = field(default_factory=list)


def resolve_exchange_profile() -> ExchangeProfile:
    """Resolve MARKET_TYPE + EXCHANGE_MODE → endpoint and API key env var names.

    Raises ValueError for unknown MARKET_TYPE values.
    """
    raw_market = os.getenv("MARKET_TYPE", "futures").lower().strip()
    exchange_mode = os.getenv("EXCHANGE_MODE", "paper").lower().strip()

    market_type = _MARKET_TYPE_ALIASES.get(raw_market)
    if market_type is None:
        raise ValueError(
            f"Unknown MARKET_TYPE={raw_market!r}. Accepted: spot, futures, usdm_futures"
        )

    is_spot = market_type == "spot"

    if exchange_mode == "demo":
        if is_spot:
            endpoint_base = _SPOT_DEMO_BASE
            api_key_env = "BINANCE_SPOT_DEMO_API_KEY"
            api_secret_env = "BINANCE_SPOT_DEMO_API_SECRET"
        else:
            endpoint_base = _FUTURES_DEMO_BASE
            api_key_env = "BINANCE_FUTURES_DEMO_API_KEY"
            api_secret_env = "BINANCE_FUTURES_DEMO_API_SECRET"

    elif exchange_mode == "testnet":
        if is_spot:
            endpoint_base = _SPOT_TESTNET_BASE
            api_key_env = "BINANCE_SPOT_TESTNET_API_KEY"
            api_secret_env = "BINANCE_SPOT_TESTNET_API_SECRET"
        else:
            endpoint_base = os.getenv("BINANCE_FUTURES_BASE_URL", _FUTURES_DEMO_BASE).rstrip("/")
            api_key_env = "BINANCE_TESTNET_API_KEY"
            api_secret_env = "BINANCE_TESTNET_API_SECRET"

    elif exchange_mode == "live":
        endpoint_base = _SPOT_LIVE_BASE if is_spot else _FUTURES_LIVE_BASE
        api_key_env = "BINANCE_LIVE_API_KEY"
        api_secret_env = "BINANCE_LIVE_API_SECRET"

    else:  # paper — no real network endpoint
        endpoint_base = ""
        api_key_env = ""
        api_secret_env = ""

    return ExchangeProfile(
        market_type=market_type,
        exchange_mode=exchange_mode,
        endpoint_base=endpoint_base,
        api_key_env=api_key_env,
        api_secret_env=api_secret_env,
        is_demo=exchange_mode in ("demo", "testnet"),
        is_spot=is_spot,
    )


def _resolve_demo_api_key(profile: ExchangeProfile) -> str:
    if profile.is_spot:
        return os.getenv(profile.api_key_env, "") or os.getenv("BINANCE_DEMO_API_KEY", "")
    return (
        os.getenv(profile.api_key_env, "")
        or os.getenv("BINANCE_DEMO_API_KEY", "")
        or os.getenv("BINANCE_TESTNET_API_KEY", "")
    )


def _resolve_demo_api_secret(profile: ExchangeProfile) -> str:
    if profile.is_spot:
        return os.getenv(profile.api_secret_env, "") or os.getenv("BINANCE_DEMO_API_SECRET", "")
    return (
        os.getenv(profile.api_secret_env, "")
        or os.getenv("BINANCE_DEMO_API_SECRET", "")
        or os.getenv("BINANCE_TESTNET_API_SECRET", "")
    )


def _resolve_testnet_api_key(profile: ExchangeProfile) -> str:
    if profile.is_spot:
        allow_demo_fallback = (
            os.getenv("BINANCE_SPOT_TESTNET_ALLOW_DEMO_FALLBACK", "false").lower() == "true"
        )
        key = os.getenv(profile.api_key_env, "") or os.getenv("BINANCE_TESTNET_API_KEY", "")
        if not key and allow_demo_fallback:
            key = os.getenv("BINANCE_SPOT_DEMO_API_KEY", "") or os.getenv("BINANCE_DEMO_API_KEY", "")
        return key
    return (
        os.getenv(profile.api_key_env, "")
        or os.getenv("BINANCE_TESTNET_API_KEY", "")
        or os.getenv("BINANCE_FUTURES_DEMO_API_KEY", "")
        or os.getenv("BINANCE_DEMO_API_KEY", "")
    )


def _resolve_testnet_api_secret(profile: ExchangeProfile) -> str:
    if profile.is_spot:
        allow_demo_fallback = (
            os.getenv("BINANCE_SPOT_TESTNET_ALLOW_DEMO_FALLBACK", "false").lower() == "true"
        )
        secret = os.getenv(profile.api_secret_env, "") or os.getenv("BINANCE_TESTNET_API_SECRET", "")
        if not secret and allow_demo_fallback:
            secret = os.getenv("BINANCE_SPOT_DEMO_API_SECRET", "") or os.getenv("BINANCE_DEMO_API_SECRET", "")
        return secret
    return (
        os.getenv(profile.api_secret_env, "")
        or os.getenv("BINANCE_TESTNET_API_SECRET", "")
        or os.getenv("BINANCE_FUTURES_DEMO_API_SECRET", "")
        or os.getenv("BINANCE_DEMO_API_SECRET", "")
    )


def _resolve_api_key(profile: ExchangeProfile) -> str:
    """Return the API key for profile, with explicit environment-aware fallback."""
    if profile.exchange_mode == "demo":
        return _resolve_demo_api_key(profile)
    if profile.exchange_mode == "testnet":
        return _resolve_testnet_api_key(profile)
    return os.getenv(profile.api_key_env, "")


def _resolve_api_secret(profile: ExchangeProfile) -> str:
    """Return the API secret for profile, with explicit environment-aware fallback."""
    if profile.exchange_mode == "demo":
        return _resolve_demo_api_secret(profile)
    if profile.exchange_mode == "testnet":
        return _resolve_testnet_api_secret(profile)
    return os.getenv(profile.api_secret_env, "")


def validate_demo_routing() -> RoutingValidation:
    """Validate that the current env config is safe before placing a non-live order.

    Checks performed (all fail-closed):
    1. MARKET_TYPE is set and recognised.
    2. Production endpoints are never used in demo/testnet mode.
    3. Spot market cannot route to a futures endpoint.
    4. Futures market cannot route to a spot endpoint.
    5. Live API key must not be reused in demo/testnet mode.
    6. Live mode requires LIVE_TRADING_ENABLED=true.

    Returns a RoutingValidation. Callers should block execution when
    ``passed`` is False and surface ``errors`` in the run log.
    """
    errors: list[str] = []

    market_type_raw = os.getenv("MARKET_TYPE", "").lower().strip()
    if not market_type_raw:
        return RoutingValidation(
            passed=False,
            profile=None,
            errors=["ROUTING_GUARD: MARKET_TYPE env var is not set — blocked"],
        )

    try:
        profile = resolve_exchange_profile()
    except ValueError as exc:
        return RoutingValidation(passed=False, profile=None, errors=[str(exc)])

    exchange_mode = profile.exchange_mode
    live_trading_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"

    # Guard 1: production endpoint must never appear in demo/testnet mode.
    if exchange_mode in ("demo", "testnet") and profile.endpoint_base in _PRODUCTION_ENDPOINTS:
        errors.append(
            f"ROUTING_GUARD: production endpoint {profile.endpoint_base!r} selected while "
            f"EXCHANGE_MODE={exchange_mode} — blocked to prevent real-money orders"
        )

    # Guard 2: spot must not route to a futures endpoint.
    if (
        exchange_mode in ("demo", "testnet")
        and profile.is_spot
        and "demo-fapi.binance.com" in profile.endpoint_base
    ):
        errors.append(
            f"ROUTING_GUARD: spot market routed to futures endpoint "
            f"{profile.endpoint_base!r} — blocked"
        )

    # Guard 3: futures must not route to a spot endpoint.
    if (
        exchange_mode in ("demo", "testnet")
        and not profile.is_spot
        and (
            "testnet.binance.vision" in profile.endpoint_base
            or "demo-api.binance.com" in profile.endpoint_base
        )
    ):
        errors.append(
            f"ROUTING_GUARD: futures market routed to spot endpoint "
            f"{profile.endpoint_base!r} — blocked"
        )

    # Guard 4: spot demo and spot testnet must remain distinct.
    if exchange_mode == "demo" and profile.is_spot and "testnet.binance.vision" in profile.endpoint_base:
        errors.append(
            "ROUTING_GUARD: spot demo routed to Spot Testnet endpoint "
            f"{profile.endpoint_base!r} — blocked (use https://demo-api.binance.com/api)"
        )
    if exchange_mode == "testnet" and profile.is_spot and "demo-api.binance.com" in profile.endpoint_base:
        errors.append(
            "ROUTING_GUARD: spot testnet routed to Spot Demo endpoint "
            f"{profile.endpoint_base!r} — blocked (use https://testnet.binance.vision/api)"
        )

    # Guard 5: live API key must not be reused in demo/testnet mode.
    if exchange_mode in ("demo", "testnet") and profile.api_key_env:
        live_key = os.getenv("BINANCE_LIVE_API_KEY", "")
        resolved_key = _resolve_api_key(profile)
        if live_key and resolved_key and resolved_key == live_key:
            errors.append(
                "ROUTING_GUARD: resolved API key matches BINANCE_LIVE_API_KEY in "
                "demo/testnet mode — blocked to prevent accidental real-money orders"
            )

    # Guard 6: live mode gate.
    if exchange_mode == "live" and not live_trading_enabled:
        errors.append(
            "ROUTING_GUARD: LIVE_TRADING_ENABLED=false while EXCHANGE_MODE=live — blocked"
        )

    if errors:
        for err in errors:
            logger.error("[exchange_routing] %s", err)

    return RoutingValidation(passed=not errors, profile=profile, errors=errors)


def resolve_demo_credentials(market_type: str, exchange_mode: str = "demo") -> tuple[str, str]:
    """Return non-live credentials for the requested market and exchange mode."""
    mt = _MARKET_TYPE_ALIASES.get(market_type.lower().strip(), "futures")
    profile = ExchangeProfile(
        market_type=mt,
        exchange_mode=exchange_mode.lower().strip(),
        endpoint_base="",
        api_key_env="",
        api_secret_env="",
        is_demo=exchange_mode.lower().strip() in ("demo", "testnet"),
        is_spot=mt == "spot",
    )
    resolved = resolve_exchange_profile() if os.getenv("MARKET_TYPE") and os.getenv("EXCHANGE_MODE") else None
    if resolved and resolved.market_type == mt and resolved.exchange_mode == profile.exchange_mode:
        profile = resolved
    else:
        if profile.exchange_mode == "demo":
            profile = ExchangeProfile(
                market_type=mt,
                exchange_mode="demo",
                endpoint_base=_SPOT_DEMO_BASE if profile.is_spot else _FUTURES_DEMO_BASE,
                api_key_env="BINANCE_SPOT_DEMO_API_KEY" if profile.is_spot else "BINANCE_FUTURES_DEMO_API_KEY",
                api_secret_env="BINANCE_SPOT_DEMO_API_SECRET" if profile.is_spot else "BINANCE_FUTURES_DEMO_API_SECRET",
                is_demo=True,
                is_spot=profile.is_spot,
            )
        elif profile.exchange_mode == "testnet":
            profile = ExchangeProfile(
                market_type=mt,
                exchange_mode="testnet",
                endpoint_base=_SPOT_TESTNET_BASE if profile.is_spot else os.getenv("BINANCE_FUTURES_BASE_URL", _FUTURES_DEMO_BASE).rstrip("/"),
                api_key_env="BINANCE_SPOT_TESTNET_API_KEY" if profile.is_spot else "BINANCE_TESTNET_API_KEY",
                api_secret_env="BINANCE_SPOT_TESTNET_API_SECRET" if profile.is_spot else "BINANCE_TESTNET_API_SECRET",
                is_demo=True,
                is_spot=profile.is_spot,
            )
    return _resolve_api_key(profile), _resolve_api_secret(profile)
