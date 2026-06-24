"""Notification engine — sends multi-channel alerts for agent events.

Priority levels:
  urgent   → approval request: Discord DM + in-app sound alert
  important → run failed / budget alert: Discord channel + email
  info     → run complete: in-app only

Escalation (for urgent approvals only):
  T+0     send notification
  T+120s  reminder (if still pending)
  T+300s  auto-reject + notify manager

Usage:
    engine = NotificationEngine(db, redis_client)
    await engine.send(
        user_id=user.id,
        event="approval_request",
        title="Trade approval needed",
        body="Crypto Trader agent is waiting for trade approval on BTC/USDT",
        project_id=project_id,
        run_id=run_id,
        meta={"step_key": "trade_gate"},
    )
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.notification_config import NotificationConfig
from app.services.event_bus import AgentEvent, event_bus

logger = logging.getLogger(__name__)

_PRIORITY: dict[str, str] = {
    "approval_request": "urgent",
    "run_failed": "important",
    "budget_alert": "important",
    "budget_hard_stop": "urgent",
    "run_complete": "info",
}

_ESCALATION_TTL = 300  # seconds before auto-reject
_REMINDER_TTL = 120


class NotificationEngine:
    def __init__(self, db: AsyncSession, redis_client: object | None = None) -> None:
        self.db = db
        self._redis = redis_client

    async def send(
        self,
        *,
        user_id: UUID,
        event: str,
        title: str,
        body: str,
        project_id: UUID | None = None,
        run_id: UUID | None = None,
        meta: dict | None = None,
    ) -> None:
        """Dispatch a notification to all configured channels for the user."""
        config = await self._get_config(user_id)
        priority = _PRIORITY.get(event, "info")

        await self._send_inapp(
            user_id=user_id,
            event=event,
            title=title,
            body=body,
            priority=priority,
            project_id=project_id,
            run_id=run_id,
            meta=meta,
        )

        if (
            priority in ("urgent", "important")
            and config
            and config.discord_enabled
            and config.discord_webhook_url
        ):
            await self._send_discord(
                webhook_url=config.discord_webhook_url,
                title=title,
                body=body,
                priority=priority,
                run_id=run_id,
            )

        if priority == "urgent" and event == "approval_request":
            await self._schedule_escalation(
                user_id=user_id,
                run_id=run_id,
                project_id=project_id,
                meta=meta or {},
            )

    async def _send_inapp(
        self,
        *,
        user_id: UUID,
        event: str,
        title: str,
        body: str,
        priority: str,
        project_id: UUID | None,
        run_id: UUID | None,
        meta: dict | None,
    ) -> None:
        try:
            await event_bus.publish(
                AgentEvent(
                    event_type=f"notification.{event}",
                    project_id=project_id or UUID(int=0),
                    run_id=run_id,
                    agent_name="system",
                    data=json.dumps(
                        {
                            "title": title,
                            "body": body,
                            "priority": priority,
                            "user_id": str(user_id),
                            **(meta or {}),
                        }
                    ),
                )
            )
        except Exception as exc:
            logger.warning("NotificationEngine in-app send failed: %s", exc)

    async def _send_discord(
        self,
        *,
        webhook_url: str,
        title: str,
        body: str,
        priority: str,
        run_id: UUID | None,
    ) -> None:
        color = 0xFF0000 if priority == "urgent" else 0xFFA500
        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": body,
                    "color": color,
                    "footer": {"text": f"run_id: {run_id}" if run_id else "pixel_dream_agent"},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("NotificationEngine Discord send failed: %s", exc)

    async def _schedule_escalation(
        self,
        *,
        user_id: UUID,
        run_id: UUID | None,
        project_id: UUID | None,
        meta: dict,
    ) -> None:
        """Store escalation job in Redis for the recovery worker to pick up."""
        client = getattr(self._redis, "client", None)
        if client is None:
            return
        try:
            key = f"escalation:{run_id}"
            payload = json.dumps(
                {
                    "user_id": str(user_id),
                    "run_id": str(run_id),
                    "project_id": str(project_id),
                    "created_at": datetime.now(UTC).isoformat(),
                    "meta": meta,
                }
            )
            await client.setex(key, _ESCALATION_TTL, payload)
        except Exception as exc:
            logger.warning("NotificationEngine escalation schedule failed: %s", exc)

    async def _get_config(self, user_id: UUID) -> NotificationConfig | None:
        result = await self.db.execute(
            select(NotificationConfig).where(NotificationConfig.user_id == user_id)
        )
        return result.scalar_one_or_none()
