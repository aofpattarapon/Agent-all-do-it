"""Checkpoint engine — saves and restores mid-step agent state in Redis.

Checkpoints survive server restarts (TTL=24h). On resume, the executor can
restore partial output instead of re-running the full step from scratch.

Usage:
    engine = CheckpointEngine(redis_client)
    await engine.save(run_id, step_id, partial_output="...", tool_calls=[...])
    ...
    cp = await engine.restore(run_id, step_id)
    if cp:
        partial_output = cp["partial_output"]
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

_TTL_SECONDS = 86_400  # 24 hours


class CheckpointEngine:
    def __init__(self, redis_client: object) -> None:
        # redis_client is app.clients.redis.RedisClient — typed as object to
        # avoid a hard import dependency (the engine can be imported before
        # Redis is connected).
        self._redis = redis_client

    def _key(self, run_id: UUID, step_id: UUID) -> str:
        return f"checkpoint:{run_id}:{step_id}"

    async def save(
        self,
        run_id: UUID,
        step_id: UUID,
        *,
        partial_output: str = "",
        tool_calls: list[dict] | None = None,
        conversation_history: list[dict] | None = None,
        extra: dict | None = None,
    ) -> None:
        """Persist a checkpoint to Redis."""
        client = getattr(self._redis, "client", None)
        if client is None:
            logger.debug("CheckpointEngine: Redis not connected, skipping save")
            return
        try:
            payload = json.dumps(
                {
                    "run_id": str(run_id),
                    "step_id": str(step_id),
                    "partial_output": partial_output,
                    "tool_calls": tool_calls or [],
                    "conversation_history": conversation_history or [],
                    **(extra or {}),
                },
                ensure_ascii=False,
            )
            await client.setex(self._key(run_id, step_id), _TTL_SECONDS, payload)
        except Exception as exc:
            logger.warning("CheckpointEngine.save failed: %s", exc)

    async def restore(self, run_id: UUID, step_id: UUID) -> dict | None:
        """Retrieve a checkpoint from Redis; returns None if none exists."""
        client = getattr(self._redis, "client", None)
        if client is None:
            return None
        try:
            raw = await client.get(self._key(run_id, step_id))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("CheckpointEngine.restore failed: %s", exc)
            return None

    async def delete(self, run_id: UUID, step_id: UUID) -> None:
        """Remove a checkpoint after the step completes successfully."""
        client = getattr(self._redis, "client", None)
        if client is None:
            return
        try:
            await client.delete(self._key(run_id, step_id))
        except Exception as exc:
            logger.warning("CheckpointEngine.delete failed: %s", exc)
