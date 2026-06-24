"""Read-only trading readiness evaluation — "what will the next order do?".

Pure function of the environment (via :func:`resolve_trading_mode` and
:func:`resolve_exchange_profile`). It NEVER places an order, NEVER mutates any env
var or setting (including ``LIVE_TRADING_ENABLED`` / ``ALLOW_ORDER_EXECUTION``), and
NEVER exposes credential values — only env var name patterns.

Fail-closed semantics:
  * PAPER  → local simulation, never sends an exchange order.
  * DEMO / TESTNET → order-capable (virtual money) once credentials are configured.
  * LIVE   → order-capable only when ``LIVE_TRADING_ENABLED`` and
    ``ALLOW_ORDER_EXECUTION`` are both enabled; otherwise blocked.
  * A TRADING_MODE/EXCHANGE_MODE mismatch resolves to ``readiness="conflict"``.
  * Missing credentials (for an order-capable mode) resolve to ``readiness="not_ready"``.
"""

from __future__ import annotations

import os
from typing import Any

from app.services.exchange_routing import resolve_exchange_profile
from app.services.trading_mode import resolve_trading_mode


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _credentials_source(api_key_env: str) -> str:
    """Derive a non-secret env var *pattern* from the API key env var name.

    e.g. ``BINANCE_FUTURES_DEMO_API_KEY`` -> ``BINANCE_FUTURES_DEMO_*``. Never a value.
    """
    if not api_key_env:
        return ""
    base = api_key_env
    for suffix in ("_API_KEY", "_KEY"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base}_*"


def _base_url_label(endpoint_base: str) -> str:
    if not endpoint_base:
        return "local-simulation (no endpoint)"
    return endpoint_base.replace("https://", "").replace("http://", "").split("/")[0]


def _order_destination(market_type: str, exchange_mode: str) -> str:
    if exchange_mode == "paper":
        return "Local Paper Simulation (no exchange)"
    market_word = "Futures" if market_type == "futures" else "Spot"
    mode_word = {"demo": "Demo", "testnet": "Testnet", "live": "Live"}.get(
        exchange_mode, exchange_mode.title()
    )
    return f"Binance {market_word} {mode_word}"


def evaluate_trading_readiness() -> dict[str, Any]:
    """Resolve the configured execution path into a fail-closed readiness object.

    Returns a dict matching :class:`app.schemas.readiness.TradingReadiness`.
    """
    status = resolve_trading_mode()

    try:
        profile = resolve_exchange_profile()
        market_type = profile.market_type
        api_key_env = profile.api_key_env
        api_secret_env = profile.api_secret_env
        endpoint_base = profile.endpoint_base
        profile_error: str | None = None
    except ValueError as exc:
        # Unknown MARKET_TYPE — fail closed with a blocking reason, no secrets involved.
        market_type = os.getenv("MARKET_TYPE", "") or "unknown"
        api_key_env = api_secret_env = endpoint_base = ""
        profile_error = str(exc)

    exchange_mode = status.exchange_mode
    is_paper = status.is_local_simulation
    is_order_capable = status.is_order_capable
    live_trading_enabled = _env_bool("LIVE_TRADING_ENABLED", default=False)
    allow_order_execution = _env_bool("ALLOW_ORDER_EXECUTION", default=True)
    mode_conflict = status.conflict is not None

    blocking_reasons: list[str] = []
    warnings: list[str] = []

    if profile_error:
        blocking_reasons.append(profile_error)
    if mode_conflict and status.conflict:
        blocking_reasons.append(status.conflict)

    # Credentials: paper needs none. Order-capable modes require key + secret present.
    if is_paper:
        credentials_source = ""
        credentials_configured = True
    else:
        credentials_source = _credentials_source(api_key_env)
        key_present = bool(os.getenv(api_key_env, "")) if api_key_env else False
        secret_present = bool(os.getenv(api_secret_env, "")) if api_secret_env else False
        credentials_configured = key_present and secret_present
        if not credentials_configured:
            blocking_reasons.append(
                f"Exchange credentials not configured (set env vars matching {credentials_source})"
            )

    # Live mode is fail-closed unless both explicit live flags are enabled.
    live_flags_ok = True
    if status.is_live:
        if not live_trading_enabled:
            blocking_reasons.append(
                "LIVE_TRADING_ENABLED is false — live order placement is fail-closed"
            )
            live_flags_ok = False
        if not allow_order_execution:
            blocking_reasons.append("ALLOW_ORDER_EXECUTION is false — order execution disabled")
            live_flags_ok = False

    # Will the next order actually reach an exchange?
    if is_paper or not is_order_capable:
        will_send_exchange_order = False
    elif status.is_live:
        will_send_exchange_order = bool(
            credentials_configured and not mode_conflict and not profile_error and live_flags_ok
        )
    else:  # demo / testnet — virtual money, order-capable once configured
        will_send_exchange_order = bool(
            credentials_configured and not mode_conflict and not profile_error
        )

    # Readiness verdict (conflict takes precedence over generic not_ready).
    if mode_conflict:
        readiness = "conflict"
    elif blocking_reasons:
        readiness = "not_ready"
    else:
        readiness = "ready"

    if will_send_exchange_order:
        if status.is_live:
            warnings.append("LIVE MODE: real-money orders will be placed on the exchange.")
        else:
            warnings.append(
                "Order-capable: virtual orders will be submitted to the exchange demo/testnet endpoint."
            )

    return {
        "trading_mode": status.trading_mode,
        "exchange_mode": exchange_mode,
        "market_type": market_type,
        "is_paper": is_paper,
        "is_demo": status.is_demo,
        "is_testnet": status.is_testnet,
        "is_live": status.is_live,
        "is_order_capable": is_order_capable,
        "live_trading_enabled": live_trading_enabled,
        "will_send_exchange_order": will_send_exchange_order,
        "order_destination": _order_destination(market_type, exchange_mode),
        "base_url_label": _base_url_label(endpoint_base),
        "credentials_configured": credentials_configured,
        "credentials_source": credentials_source,
        "credential_values_exposed": False,
        "mode_conflict": mode_conflict,
        "readiness": readiness,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }
