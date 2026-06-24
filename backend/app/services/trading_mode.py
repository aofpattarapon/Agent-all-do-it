"""Authoritative trading mode resolution.

Single source of truth for all execution path mode decisions.
EXCHANGE_MODE is the primary var (used by exchange_tool.place_order).
TRADING_MODE (used by ExecutionService) is validated against it for consistency.
Fail closed on mode disagreement.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Valid values for each env var.
_VALID_EXCHANGE_MODES = frozenset({"paper", "demo", "testnet", "live"})
_VALID_TRADING_MODES = frozenset({"PAPER", "DEMO", "TESTNET", "LIVE"})

# Redis keys for runtime trading-mode overrides.
_REDIS_TRADING_MODE_KEY = "trading:trading_mode"
_REDIS_EXCHANGE_MODE_KEY = "trading:exchange_mode"

_redis_sync_client: redis.Redis | None = None


def _get_redis_sync_client() -> redis.Redis | None:
    """Lazy singleton for a synchronous Redis client used to read runtime overrides."""
    global _redis_sync_client
    if _redis_sync_client is None:
        try:
            _redis_sync_client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not create sync Redis client: %s", exc)
            _redis_sync_client = None
    return _redis_sync_client


def _read_redis_mode_overrides() -> tuple[str | None, str | None]:
    """Read trading/exchange mode overrides from Redis.

    Returns (trading_mode, exchange_mode) or (None, None) if Redis is unavailable
    or the keys are not set.
    """
    client = _get_redis_sync_client()
    if client is None:
        return None, None
    try:
        values = client.mget([_REDIS_TRADING_MODE_KEY, _REDIS_EXCHANGE_MODE_KEY])
    except Exception as exc:
        logger.debug("Redis trading-mode read failed, falling back to env: %s", exc)
        return None, None
    trading_mode = values[0].strip().upper() if values[0] else None
    exchange_mode = values[1].strip().lower() if values[1] else None
    return trading_mode, exchange_mode

# Maps TRADING_MODE → the EXCHANGE_MODE it is allowed to drive.
#
# STRICT 1:1. This is the Phase 2B safety boundary: ``PAPER`` is LOCAL SIMULATION
# ONLY and must never accept an order-capable exchange mode. ``PAPER + demo`` (the
# previously-accepted dangerous mixed mode that could still place real Binance demo
# orders) now resolves to a hard conflict — DEMO is its own first-class, order-capable
# mode and must be selected explicitly via ``TRADING_MODE=DEMO``.
_TRADING_TO_EXCHANGE: dict[str, frozenset[str]] = {
    "PAPER": frozenset({"paper"}),
    "DEMO": frozenset({"demo"}),
    "TESTNET": frozenset({"testnet"}),
    "LIVE": frozenset({"live"}),
}


def validate_trading_mode_pair(trading_mode: str, exchange_mode: str) -> None:
    """Validate a TRADING_MODE/EXCHANGE_MODE pair.

    Raises ValueError with a descriptive message if the pair is invalid or conflicts.
    """
    trading_mode = trading_mode.upper().strip()
    exchange_mode = exchange_mode.lower().strip()

    if trading_mode not in _VALID_TRADING_MODES:
        raise ValueError(f"TRADING_MODE={trading_mode!r} is not valid")
    if exchange_mode not in _VALID_EXCHANGE_MODES:
        raise ValueError(f"EXCHANGE_MODE={exchange_mode!r} is not valid")

    expected = _TRADING_TO_EXCHANGE.get(trading_mode, frozenset())
    if exchange_mode not in expected:
        raise ValueError(
            f"TRADING_MODE={trading_mode} expects EXCHANGE_MODE in {sorted(expected)}, "
            f"got EXCHANGE_MODE={exchange_mode!r}"
        )


def write_trading_mode_overrides(trading_mode: str, exchange_mode: str) -> None:
    """Write validated trading-mode overrides to Redis.

    Processes that call :func:`resolve_trading_mode` will pick these up immediately.
    """
    validate_trading_mode_pair(trading_mode, exchange_mode)
    client = _get_redis_sync_client()
    if client is None:
        raise RuntimeError("Redis is not available; cannot apply runtime trading-mode override")
    client.set(_REDIS_TRADING_MODE_KEY, trading_mode.upper().strip())
    client.set(_REDIS_EXCHANGE_MODE_KEY, exchange_mode.lower().strip())


def delete_trading_mode_overrides() -> None:
    """Remove Redis trading-mode overrides so the system falls back to environment variables."""
    client = _get_redis_sync_client()
    if client is None:
        return
    client.delete(_REDIS_TRADING_MODE_KEY, _REDIS_EXCHANGE_MODE_KEY)


async def sync_db_trading_mode_to_redis() -> None:
    """Push any persisted DB trading-mode overrides into Redis on startup.

    This ensures Celery workers and the API see the same runtime values without
    requiring an explicit PATCH after a restart.
    """
    from app.db.session import get_db_context
    from app.services.app_setting import AppSettingService

    try:
        async with get_db_context() as db:
            svc = AppSettingService(db)
            cfg = await svc.get_trading_mode_config()
            trading_mode = cfg.get("trading_mode")
            exchange_mode = cfg.get("exchange_mode")
            if trading_mode and exchange_mode:
                write_trading_mode_overrides(trading_mode, exchange_mode)
                logger.info(
                    "Synced DB trading-mode override to Redis: %s / %s",
                    trading_mode,
                    exchange_mode,
                )
    except Exception as exc:
        logger.warning("Could not sync DB trading-mode overrides to Redis: %s", exc)


@dataclass(frozen=True)
class TradingModeStatus:
    exchange_mode: str
    trading_mode: str
    is_live: bool
    is_demo: bool
    is_testnet: bool
    # ``is_local_simulation`` is the ONLY flag that means "no external exchange order
    # is ever placed" (paper). ``is_order_capable`` means a real order can be submitted
    # to an exchange venue (demo/testnet/live — virtual money for demo/testnet, real for live).
    is_local_simulation: bool
    is_order_capable: bool
    # Back-compat alias of ``is_local_simulation``. Historically ``is_paper`` was True for
    # both paper AND demo, which is exactly the conflation Phase 2B removes — it now means
    # local simulation only. Prefer ``is_local_simulation``/``is_order_capable`` in new code.
    is_paper: bool
    conflict: str | None
    # Where the active values came from: "runtime" (Redis/DB override) or "environment".
    source: str


def resolve_trading_mode() -> TradingModeStatus:
    """Read runtime overrides (Redis) then env vars and return the resolved mode."""
    redis_trading_mode, redis_exchange_mode = _read_redis_mode_overrides()

    if redis_exchange_mode is not None and redis_exchange_mode in _VALID_EXCHANGE_MODES:
        exchange_mode = redis_exchange_mode
        exchange_source = "runtime"
    else:
        exchange_mode = os.getenv("EXCHANGE_MODE", "paper").lower().strip()
        exchange_source = "environment"
        if exchange_mode not in _VALID_EXCHANGE_MODES:
            logger.warning(
                "EXCHANGE_MODE=%r is not a known value; defaulting to 'paper'", exchange_mode
            )
            exchange_mode = "paper"

    if redis_trading_mode is not None and redis_trading_mode in _VALID_TRADING_MODES:
        trading_mode = redis_trading_mode
        trading_source = "runtime"
    else:
        trading_mode = os.getenv("TRADING_MODE", "PAPER").upper().strip()
        trading_source = "environment"
        if trading_mode not in _VALID_TRADING_MODES:
            logger.warning(
                "TRADING_MODE=%r is not a known value; defaulting to 'PAPER'", trading_mode
            )
            trading_mode = "PAPER"

    source = "runtime" if trading_source == "runtime" or exchange_source == "runtime" else "environment"

    conflict: str | None = None
    expected = _TRADING_TO_EXCHANGE.get(trading_mode, frozenset())
    if exchange_mode not in expected:
        conflict = (
            f"TRADING_MODE={trading_mode} expects EXCHANGE_MODE in {sorted(expected)}, "
            f"got EXCHANGE_MODE={exchange_mode!r}"
        )
        logger.warning("Trading mode conflict: %s", conflict)

    is_live = exchange_mode == "live"
    is_demo = exchange_mode == "demo"
    is_testnet = exchange_mode == "testnet"
    is_local_simulation = exchange_mode == "paper"
    is_order_capable = exchange_mode in ("demo", "testnet", "live")

    return TradingModeStatus(
        exchange_mode=exchange_mode,
        trading_mode=trading_mode,
        is_live=is_live,
        is_demo=is_demo,
        is_testnet=is_testnet,
        is_local_simulation=is_local_simulation,
        is_order_capable=is_order_capable,
        is_paper=is_local_simulation,
        conflict=conflict,
        source=source,
    )


def assert_no_mode_conflict() -> TradingModeStatus:
    """Resolve mode and raise ValueError if the two env vars conflict.

    Call this at startup or at the beginning of any execution path that touches
    real orders, to fail closed before any order is placed.
    """
    status = resolve_trading_mode()
    if status.conflict:
        raise ValueError(f"Trading mode misconfiguration detected — {status.conflict}")
    return status


def effective_project_mode() -> str:
    """Return the canonical project_mode string for run dispatch payloads."""
    status = resolve_trading_mode()
    if status.is_live:
        return "live"
    if status.exchange_mode == "testnet":
        return "testnet"
    if status.exchange_mode == "demo":
        return "demo"
    return "paper"


# ── Runtime visibility (UI-facing) ─────────────────────────────────────────────

# Maps the authoritative EXCHANGE_MODE token → the normalized runtime_mode the UI
# uses to label "what will the next order actually do".
_RUNTIME_MODE_BY_EXCHANGE_MODE: dict[str, str] = {
    "paper": "paper_simulation",
    "demo": "exchange_demo",
    "testnet": "exchange_testnet",
    "live": "live",
}


def _env_bool(name: str, *, default: bool) -> bool:
    """Read a boolean env var (``true``/``1``/``yes``/``on`` → True)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def build_runtime_visibility() -> dict[str, Any]:
    """Build the normalized, UI-facing runtime-mode object.

    This is the single source of truth for "what mode is the *system* in and what will
    the next order do" — distinct from per-execution ``execution_visibility`` (which reports
    how a *historical* trade was actually routed). Pure function of the environment via
    :func:`resolve_trading_mode`; never touches the DB and never changes behavior.

    ``order_placement_enabled`` reports whether **real-money / live** order placement is
    enabled (``ALLOW_ORDER_EXECUTION`` *and* ``LIVE_TRADING_ENABLED``). Demo/testnet routes
    still submit *virtual* orders to the exchange — that fact is carried by
    ``is_exchange_backed`` — but they never place real-money orders, so this flag is False
    for anything other than a fully-enabled live configuration.

    ``monitoring_exchange_backed`` mirrors the PositionMonitor gate (``exchange_mode != "paper"``)
    so the UI can state whether closes are confirmed against the exchange or simulated.
    """
    status = resolve_trading_mode()
    exchange_mode = status.exchange_mode
    runtime_mode = _RUNTIME_MODE_BY_EXCHANGE_MODE.get(exchange_mode, "paper_simulation")

    market_type = os.getenv("MARKET_TYPE", "futures").strip().lower()
    if market_type not in ("spot", "futures"):
        market_type = "futures"

    exchange_raw = os.getenv("EXCHANGE", "BINANCE_FUTURES").strip().lower()
    exchange = "binance" if "binance" in exchange_raw else (exchange_raw or "binance")

    is_paper_simulation = exchange_mode == "paper"
    is_exchange_backed = exchange_mode != "paper"
    is_live = status.is_live
    order_placement_enabled = _env_bool("ALLOW_ORDER_EXECUTION", default=True) and _env_bool(
        "LIVE_TRADING_ENABLED", default=False
    )

    market_word = "Futures" if market_type == "futures" else "Spot"
    exchange_word = "Binance" if exchange == "binance" else exchange.title()
    if runtime_mode == "paper_simulation":
        label = "Paper Simulation"
    elif runtime_mode == "exchange_demo":
        label = f"{exchange_word} Demo {market_word}"
    elif runtime_mode == "exchange_testnet":
        label = f"{exchange_word} Testnet {market_word}"
    else:
        label = f"{exchange_word} Live {market_word}"

    if is_live:
        safety_label = "REAL money / live funds at risk"
    elif is_paper_simulation:
        safety_label = "Simulated / no orders placed"
    else:
        safety_label = "Virtual money / no live funds"

    return {
        "runtime_mode": runtime_mode,
        "market_type": market_type,
        "exchange": exchange,
        "exchange_environment": exchange_mode,
        "is_exchange_backed": is_exchange_backed,
        "is_paper_simulation": is_paper_simulation,
        "is_local_simulation": is_paper_simulation,
        "is_order_capable": status.is_order_capable,
        "is_demo": status.is_demo,
        "is_testnet": status.is_testnet,
        "is_live": is_live,
        "order_placement_enabled": order_placement_enabled,
        "monitoring_exchange_backed": is_exchange_backed,
        "label": label,
        "safety_label": safety_label,
        "trading_mode": status.trading_mode,
        "conflict": status.conflict,
        "source": status.source,
    }
