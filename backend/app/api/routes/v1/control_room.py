"""Control Room WebSocket — streams real-time agent events to the frontend."""

import asyncio
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import get_current_user_ws
from app.core.rbac import Permission
from app.db.models.user import User
from app.db.session import get_db_context
from app.services.event_bus import event_bus
from app.services.project import ProjectService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/control/{project_id}")
async def control_room_ws(
    websocket: WebSocket,
    project_id: UUID,
    user: Annotated[User, Depends(get_current_user_ws)],
) -> None:
    """Stream agent events to connected Control Room clients."""

    # Accept using the subprotocol set by get_current_user_ws
    subprotocol = getattr(websocket.state, "accept_subprotocol", None)
    await websocket.accept(subprotocol=subprotocol)

    # Verify project ownership
    async with get_db_context() as db:
        svc = ProjectService(db)
        try:
            await svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
        except Exception:
            await websocket.close(code=4003, reason="Project not found")
            return

    pid = str(project_id)
    q = event_bus.subscribe(pid)
    logger.info("Control room connected: project=%s user=%s", pid, user.email)

    try:
        await websocket.send_json({"type": "connected", "project_id": pid})
        for event in event_bus.recent(pid):
            await websocket.send_json({
                "type": event.type,
                "project_id": event.project_id,
                "run_id": event.run_id,
                "task": event.task,
                "agent_name": event.agent_name,
                "agent_role": event.agent_role,
                "data": event.data,
                "timestamp": event.timestamp,
            })
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=25.0)
                await websocket.send_json({
                    "type": event.type,
                    "project_id": event.project_id,
                    "run_id": event.run_id,
                    "task": event.task,
                    "agent_name": event.agent_name,
                    "agent_role": event.agent_role,
                    "data": event.data,
                    "timestamp": event.timestamp,
                })
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        logger.info("Control room disconnected: project=%s", pid)
    finally:
        event_bus.unsubscribe(pid, q)
