"""Project-configurable warmup-mode policy for the Auto winrate/warmup gate (Phase 6.14.W22E).

The Auto trade pipeline's ``winrate_trade_gate`` auto-executes during the warmup window
(``closed_count < warmup_trades``) regardless of winrate. This module makes that warmup
behavior project-configurable and fail-closed, WITHOUT changing the post-warmup winrate logic.

Modes:
* ``auto_execute``     — legacy behavior: a valid warmup proposal auto-executes.
* ``pending_approval`` — DEFAULT: route to the existing approval/waiting path; no order placed.
* ``validation_only``  — record a safe no-order validation result; no order placed.

Resolution order (first usable value wins):
1. project-level setting in ``app_settings`` (key ``pipeline.warmup_mode:{project_id}``)
2. workflow node config ``warmup_mode``
3. env/default ``settings.PIPELINE_WARMUP_MODE``
4. hard fallback ``pending_approval``

Fail-closed contract: an explicitly-set but invalid/malformed value at any level resolves to
``pending_approval`` (it never silently falls through to a more permissive level, and never
silently becomes ``auto_execute``); any read/DB error resolves to ``pending_approval`` too.
An *absent* value at a level (no row / key not present) falls through to the next level — only a
*present-but-invalid* value fails closed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from app.repositories import app_setting_repo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

WarmupMode = Literal["auto_execute", "pending_approval", "validation_only"]
WarmupAction = Literal["auto_execute", "validation_only", "pending_approval", "below_threshold"]

VALID_WARMUP_MODES: frozenset[str] = frozenset(
    {"auto_execute", "pending_approval", "validation_only"}
)
DEFAULT_WARMUP_MODE: WarmupMode = "pending_approval"
_KEY_PREFIX = "pipeline.warmup_mode:"


def warmup_mode_key(project_id: UUID) -> str:
    """Project-scoped app_settings key for the warmup-mode override."""
    return f"{_KEY_PREFIX}{project_id}"


def normalize_warmup_mode(value: Any) -> WarmupMode | None:
    """Return the recognized warmup mode for ``value``, or None if it is not a valid mode.

    ``None`` means "not a usable mode here"; the caller decides whether that is an *absent*
    value (fall through to the next source) or a *present-but-invalid* value (fail closed).
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    if candidate in VALID_WARMUP_MODES:
        return candidate  # type: ignore[return-value]
    return None


async def resolve_warmup_mode(
    db: AsyncSession,
    project_id: UUID,
    workflow_config: dict[str, Any] | None,
) -> WarmupMode:
    """Resolve the effective warmup mode for ``project_id``; fail-closed to pending_approval."""
    # 1. project-level app_settings override
    try:
        raw = await app_setting_repo.get_value(db, warmup_mode_key(project_id), "")
    except Exception as exc:  # fail closed on any read/DB error
        logger.warning(
            "warmup_mode: project-setting read failed for %s (%s); failing closed to %s",
            project_id,
            exc,
            DEFAULT_WARMUP_MODE,
        )
        return DEFAULT_WARMUP_MODE
    if raw and raw.strip():
        mode = normalize_warmup_mode(raw)
        if mode is None:
            logger.warning(
                "warmup_mode: invalid project setting %r for %s; failing closed to %s",
                raw,
                project_id,
                DEFAULT_WARMUP_MODE,
            )
            return DEFAULT_WARMUP_MODE
        return mode

    # 2. workflow node config
    cfg_value = (workflow_config or {}).get("warmup_mode")
    if cfg_value is not None:
        mode = normalize_warmup_mode(cfg_value)
        if mode is None:
            logger.warning(
                "warmup_mode: invalid workflow-config value %r; failing closed to %s",
                cfg_value,
                DEFAULT_WARMUP_MODE,
            )
            return DEFAULT_WARMUP_MODE
        return mode

    # 3. env/default
    from app.core.config import settings

    env_mode = normalize_warmup_mode(getattr(settings, "PIPELINE_WARMUP_MODE", None))
    if env_mode is not None:
        return env_mode

    # 4. hard fallback (env absent or invalid)
    return DEFAULT_WARMUP_MODE


def decide_warmup_action(
    *,
    in_warmup: bool,
    winrate_pass: bool,
    warmup_mode: WarmupMode,
) -> WarmupAction:
    """Pure decision for the winrate gate.

    During warmup, dispatch on the (already resolved + validated) ``warmup_mode``. Past warmup,
    return ``auto_execute`` when the winrate passed and ``below_threshold`` otherwise — leaving
    the existing post-warmup skip/pause logic untouched. An unrecognized ``warmup_mode`` during
    warmup is treated as ``pending_approval`` (fail-closed; never ``auto_execute``).
    """
    if in_warmup:
        if warmup_mode == "auto_execute":
            return "auto_execute"
        if warmup_mode == "validation_only":
            return "validation_only"
        return "pending_approval"
    return "auto_execute" if winrate_pass else "below_threshold"
