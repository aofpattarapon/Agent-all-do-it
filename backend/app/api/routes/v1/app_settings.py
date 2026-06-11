"""App settings routes — AI backend configuration."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AppSettingSvc, CurrentAdmin
from app.core.runtime_catalog import normalize_runtime_model_pair

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
    openrouter_api_key_set: bool
    ollama_url: str


class AiConfigUpdate(BaseModel):
    default_backend: str | None = None
    anthropic_api_key: str | None = None
    default_model: str | None = None
    auto_fallback: bool | None = None
    moonshot_api_key: str | None = None
    groq_api_key: str | None = None
    openrouter_api_key: str | None = None
    ollama_url: str | None = None


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
        openrouter_api_key_set=bool(cfg["openrouter_api_key"]),
        ollama_url=cfg["ollama_url"],
    )


@router.patch("/settings/ai", response_model=AiConfigRead)
async def update_ai_config(body: AiConfigUpdate, user: CurrentAdmin, svc: AppSettingSvc) -> Any:
    current = await svc.get_ai_config()
    requested_backend = body.default_backend if body.default_backend is not None else current["default_backend"]
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
        openrouter_api_key_set=bool(cfg["openrouter_api_key"]),
        ollama_url=cfg["ollama_url"],
    )
