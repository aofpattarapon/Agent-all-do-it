"""App settings routes — AI backend configuration."""

import os
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import AppSettingSvc, CurrentAdmin
from app.core.runtime_catalog import normalize_runtime_model_pair
from app.services.trading_mode import (
    effective_project_mode,
    resolve_trading_mode,
    validate_trading_mode_pair,
    write_trading_mode_overrides,
)

router = APIRouter()


class SettingRead(BaseModel):
    key: str
    value: str
    description: str


class SettingUpdate(BaseModel):
    value: str


class AiConfigRead(BaseModel):
    default_backend: str
    anthropic_api_key_set: bool
    default_model: str
    auto_fallback: bool
    moonshot_api_key_set: bool
    groq_api_key_set: bool
    cerebras_api_key_set: bool
    google_api_key_set: bool
    openrouter_api_key_set: bool
    ollama_url: str


class AiConfigUpdate(BaseModel):
    default_backend: str | None = None
    anthropic_api_key: str | None = None
    default_model: str | None = None
    auto_fallback: bool | None = None
    moonshot_api_key: str | None = None
    groq_api_key: str | None = None
    cerebras_api_key: str | None = None
    google_api_key: str | None = None
    openrouter_api_key: str | None = None
    ollama_url: str | None = None


class TradingModeConfigRead(BaseModel):
    trading_mode: str
    exchange_mode: str
    resolved_runtime_mode: str
    conflict: str | None
    source: str
    db_overrides: dict[str, str | None]
    environment: dict[str, Any]


class TradingModeConfigUpdate(BaseModel):
    trading_mode: str
    exchange_mode: str
    confirm_live: bool = False


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _trading_environment_flags() -> dict[str, Any]:
    return {
        "allow_order_execution": _env_bool("ALLOW_ORDER_EXECUTION", default=True),
        "live_trading_enabled": _env_bool("LIVE_TRADING_ENABLED", default=False),
        "market_type": os.getenv("MARKET_TYPE", "futures").strip().lower(),
        "exchange": os.getenv("EXCHANGE", "BINANCE_FUTURES").strip(),
    }


@router.get("/settings", response_model=list[SettingRead])
async def list_settings(user: CurrentAdmin, svc: AppSettingSvc) -> Any:
    rows = await svc.list()
    return [
        SettingRead(
            key=r.key,
            value="***" if "key" in r.key and r.value else r.value,
            description=r.description,
        )
        for r in rows
    ]


@router.get("/settings/ai", response_model=AiConfigRead)
async def get_ai_config(user: CurrentAdmin, svc: AppSettingSvc) -> Any:
    cfg = await svc.get_ai_config()
    return AiConfigRead(
        default_backend=cfg["default_backend"],
        anthropic_api_key_set=bool(cfg["anthropic_api_key"]),
        default_model=cfg["default_model"],
        auto_fallback=cfg["auto_fallback"],
        moonshot_api_key_set=bool(cfg["moonshot_api_key"]),
        groq_api_key_set=bool(cfg["groq_api_key"]),
        cerebras_api_key_set=bool(cfg["cerebras_api_key"]),
        google_api_key_set=bool(cfg["google_api_key"]),
        openrouter_api_key_set=bool(cfg["openrouter_api_key"]),
        ollama_url=cfg["ollama_url"],
    )


@router.patch("/settings/ai", response_model=AiConfigRead)
async def update_ai_config(body: AiConfigUpdate, user: CurrentAdmin, svc: AppSettingSvc) -> Any:
    current = await svc.get_ai_config()
    requested_backend = (
        body.default_backend if body.default_backend is not None else current["default_backend"]
    )
    requested_model = body.default_model
    if requested_model is None:
        if body.default_backend is not None and body.default_backend != current["default_backend"]:
            requested_model = ""
        else:
            requested_model = current["default_model"]
    normalized_backend, normalized_model = normalize_runtime_model_pair(
        requested_backend,
        requested_model,
    )

    if body.default_backend is not None:
        await svc.set("ai.default_backend", normalized_backend)
    if body.anthropic_api_key is not None:
        await svc.set("ai.anthropic_api_key", body.anthropic_api_key)
    if body.default_backend is not None or body.default_model is not None:
        await svc.set("ai.default_model", normalized_model)
    if body.auto_fallback is not None:
        await svc.set("ai.auto_fallback", "true" if body.auto_fallback else "false")
    if body.moonshot_api_key is not None:
        await svc.set("ai.moonshot_api_key", body.moonshot_api_key)
    if body.groq_api_key is not None:
        await svc.set("ai.groq_api_key", body.groq_api_key)
    if body.cerebras_api_key is not None:
        await svc.set("ai.cerebras_api_key", body.cerebras_api_key)
    if body.google_api_key is not None:
        await svc.set("ai.google_api_key", body.google_api_key)
    if body.openrouter_api_key is not None:
        await svc.set("ai.openrouter_api_key", body.openrouter_api_key)
    if body.ollama_url is not None:
        await svc.set("ai.ollama_url", body.ollama_url)

    cfg = await svc.get_ai_config()
    return AiConfigRead(
        default_backend=cfg["default_backend"],
        anthropic_api_key_set=bool(cfg["anthropic_api_key"]),
        default_model=cfg["default_model"],
        auto_fallback=cfg["auto_fallback"],
        moonshot_api_key_set=bool(cfg["moonshot_api_key"]),
        groq_api_key_set=bool(cfg["groq_api_key"]),
        cerebras_api_key_set=bool(cfg["cerebras_api_key"]),
        google_api_key_set=bool(cfg["google_api_key"]),
        openrouter_api_key_set=bool(cfg["openrouter_api_key"]),
        ollama_url=cfg["ollama_url"],
    )


@router.get("/settings/trading", response_model=TradingModeConfigRead)
async def get_trading_mode_config(user: CurrentAdmin, svc: AppSettingSvc) -> Any:
    """Return the currently active trading-mode configuration and its source."""
    resolved = resolve_trading_mode()
    db_cfg = await svc.get_trading_mode_config()
    return TradingModeConfigRead(
        trading_mode=resolved.trading_mode,
        exchange_mode=resolved.exchange_mode,
        resolved_runtime_mode=effective_project_mode(),
        conflict=resolved.conflict,
        source=resolved.source,
        db_overrides=db_cfg,
        environment=_trading_environment_flags(),
    )


@router.patch("/settings/trading", response_model=TradingModeConfigRead)
async def update_trading_mode_config(
    body: TradingModeConfigUpdate, user: CurrentAdmin, svc: AppSettingSvc
) -> Any:
    """Update the runtime trading-mode configuration.

    Writes to both the database (persistence) and Redis (immediate propagation to
    all backend/Celery processes). Mismatched pairs are rejected.
    """
    try:
        validate_trading_mode_pair(body.trading_mode, body.exchange_mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    trading_mode = body.trading_mode.upper().strip()
    exchange_mode = body.exchange_mode.lower().strip()

    if trading_mode == "LIVE" and not body.confirm_live:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LIVE mode requires confirm_live=true",
        )

    await svc.set_trading_mode_config(trading_mode, exchange_mode)
    try:
        write_trading_mode_overrides(trading_mode, exchange_mode)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Saved to database but could not propagate to Redis: {exc}",
        ) from exc

    resolved = resolve_trading_mode()
    db_cfg = await svc.get_trading_mode_config()
    return TradingModeConfigRead(
        trading_mode=resolved.trading_mode,
        exchange_mode=resolved.exchange_mode,
        resolved_runtime_mode=effective_project_mode(),
        conflict=resolved.conflict,
        source=resolved.source,
        db_overrides=db_cfg,
        environment=_trading_environment_flags(),
    )
