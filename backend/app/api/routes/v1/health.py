"""Health check endpoints.

Provides Kubernetes-compatible health check endpoints:
- /health - Simple liveness check
- /health/live - Detailed liveness probe
- /health/ready - Readiness probe with dependency checks
"""
# ruff: noqa: I001 - Imports structured for Jinja2 template conditionals

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.api.deps import DBSession, Redis
from app.core.config import settings
from app.services.health import build_health_response
from app.services.runtime import healthcheck_all

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Simple liveness probe - check if application is running.

    This is a lightweight check that should always succeed if the
    application is running. Use this for basic connectivity tests.

    Returns:
        {"status": "healthy"}
    """
    return {
        "status": "healthy",
        "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
    }


@router.get("/health/live")
async def liveness_probe() -> dict[str, Any]:
    """Detailed liveness probe for Kubernetes.

    This endpoint is designed for Kubernetes liveness probes.
    It checks if the application process is alive and responding.
    Failure indicates the container should be restarted.

    Returns:
        Structured response with timestamp and service info.
    """
    return build_health_response(
        status="alive",
        details={
            "version": getattr(settings, "VERSION", "1.0.0"),
            "environment": settings.ENVIRONMENT,
        },
    )


@router.get("/health/ready", response_model=None)
async def readiness_probe(
    db: DBSession,
    redis: Redis,
) -> dict[str, Any] | JSONResponse:
    """Readiness probe for Kubernetes.

    This endpoint checks if all dependencies are ready to handle traffic.
    It verifies database connections, Redis, and other critical services.
    Failure indicates traffic should be temporarily diverted.

    Checks performed:
    - Database connectivity
    - Redis connectivity

    Returns:
        Structured response with individual check results.
        Returns 503 if any critical check fails.
    """
    checks: dict[str, dict[str, Any]] = {}
    # Database check
    try:
        start = datetime.now(UTC)
        await db.execute(text("SELECT 1"))
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        checks["database"] = {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
            "type": "postgresql",
        }
    except Exception as e:
        checks["database"] = {
            "status": "unhealthy",
            "error": str(e),
            "type": "postgresql",
        }
    # Redis check
    try:
        start = datetime.now(UTC)
        is_healthy = await redis.ping()
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        if is_healthy:
            checks["redis"] = {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
            }
        else:
            checks["redis"] = {
                "status": "unhealthy",
                "error": "Ping failed",
            }
    except Exception as e:
        checks["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # LLM provider — config-only check (avoid spending money on a probe call).
    llm_provider = (getattr(settings, "LLM_PROVIDER", None) or "").lower()
    if llm_provider:
        key_field = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }.get(llm_provider)
        api_key = getattr(settings, key_field, None) if key_field else None
        checks["llm"] = {
            "status": "healthy" if api_key else "unhealthy",
            "provider": llm_provider,
            "detail": "API key configured" if api_key else "API key missing",
        }
    else:
        checks["llm"] = {"status": "unknown", "detail": "not configured"}
    # Background worker — config-only (a real probe needs an end-to-end ping).
    broker_url = getattr(settings, "CELERY_BROKER_URL", None)
    checks["worker"] = (
        {"status": "healthy", "detail": "broker configured"}
        if broker_url
        else {"status": "unknown", "detail": "not configured"}
    )

    # Determine overall health — only db + redis are critical for readiness.
    critical = {k: v for k, v in checks.items() if k in ("database", "redis")}
    all_healthy = (
        all(check.get("status") == "healthy" for check in critical.values()) if critical else True
    )

    # The admin /system page reads each service from the top level, so flatten
    # the checks alongside the structured `checks` field for K8s probes.
    response_data = build_health_response(
        status="ready" if all_healthy else "not_ready",
        checks=checks,
    )
    response_data.update(checks)

    if not all_healthy:
        return JSONResponse(status_code=503, content=response_data)

    return response_data


# Backward compatibility - keep /ready endpoint
@router.get("/ready", response_model=None)
async def readiness_check(
    db: DBSession,
    redis: Redis,
) -> dict[str, Any] | JSONResponse:
    """Readiness check (alias for /health/ready).

    Deprecated: Use /health/ready instead.
    """
    return await readiness_probe(
        db=db,
        redis=redis,
    )


@router.get("/health/runtimes")
async def runtime_health_check() -> dict[str, Any]:
    """Return the health status of every runtime adapter.

    Useful for the frontend to show which backends (claude-cli, kimi-cli,
    anthropic-api, ollama, etc.) are available before the user starts a chat.
    """
    return {"runtimes": healthcheck_all()}


@router.get("/health/deep", response_model=None)
async def deep_health(request: Request, db: DBSession) -> dict[str, Any] | JSONResponse:
    """Extended health check — verifies DB, Redis, and all LLM runtime adapters.

    Returns 200 when all critical services are reachable, 503 otherwise.
    Safe to call from uptime monitors — never triggers LLM API calls.
    """
    checks: dict[str, Any] = {}

    # Database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "detail": str(exc)}

    # Redis
    try:
        redis = request.app.state.redis
        await redis.ping()
        checks["redis"] = {"ok": True}
    except Exception as exc:
        checks["redis"] = {"ok": False, "detail": str(exc)}

    # LLM runtime adapters (config-only checks — no API calls)
    checks["llm_providers"] = healthcheck_all()

    all_ok = checks["database"]["ok"] and checks["redis"]["ok"]

    return JSONResponse(
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
        status_code=200 if all_ok else 503,
    )


@router.get("/health/ollama-models")
async def ollama_models(db: DBSession) -> dict[str, Any]:
    """Return available Ollama models from the configured OLLAMA_URL.

    Reads the URL from the DB (admin UI setting) first, falling back to the
    OLLAMA_URL env var so the health check matches what the runtime actually uses.
    """
    import httpx
    from app.services.app_setting import AppSettingService

    ai_cfg = await AppSettingService(db).get_ai_config()
    base = (ai_cfg.get("ollama_url") or "http://localhost:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        return {"available": True, "base_url": base, "models": models}
    except Exception as exc:
        return {"available": False, "base_url": base, "models": [], "error": str(exc)}
