"""Room and RoomMessage routes — includes WebSocket broadcast hub."""

import asyncio
import contextlib
import logging
from collections import defaultdict
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status

from app.api.deps import CurrentUser, ProjectSvc, RoomSvc, get_current_user_ws
from app.core.rbac import Permission
from app.db.models.user import User
from app.db.session import get_db_context
from app.schemas.room import (
    RoomCreate,
    RoomList,
    RoomMessageCreate,
    RoomMessageList,
    RoomMessageRead,
    RoomRead,
    RoomUpdate,
)
from app.services.project import ProjectService
from app.services.room import RoomService

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Room WebSocket Hub ────────────────────────────────────────────────────────


class _RoomHub:
    """Fan-out broadcast hub: one queue per connected WebSocket client, keyed by room_id."""

    def __init__(self) -> None:
        self._rooms: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def join(self, room_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._rooms[room_id].append(q)
        return q

    def leave(self, room_id: str, q: asyncio.Queue) -> None:
        with contextlib.suppress(ValueError):
            self._rooms[room_id].remove(q)

    async def broadcast(self, room_id: str, payload: dict) -> None:
        for q in list(self._rooms.get(room_id, [])):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(payload)


room_hub = _RoomHub()


# ── Rooms ─────────────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/rooms", response_model=RoomList)
async def list_rooms(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    room_svc: RoomSvc,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    items, total = await room_svc.list(project_id, skip=skip, limit=limit)
    return RoomList(items=items, total=total)


@router.post(
    "/projects/{project_id}/rooms",
    response_model=RoomRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_room(
    project_id: UUID,
    data: RoomCreate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    room_svc: RoomSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)
    return await room_svc.create(project_id, data)


@router.get("/projects/{project_id}/rooms/{room_id}", response_model=RoomRead)
async def get_room(
    project_id: UUID,
    room_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    room_svc: RoomSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    return await room_svc.get(room_id, project_id)


@router.patch("/projects/{project_id}/rooms/{room_id}", response_model=RoomRead)
async def update_room(
    project_id: UUID,
    room_id: UUID,
    data: RoomUpdate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    room_svc: RoomSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)
    return await room_svc.update(room_id, project_id, data)


@router.delete(
    "/projects/{project_id}/rooms/{room_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_room(
    project_id: UUID,
    room_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    room_svc: RoomSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)
    await room_svc.delete(room_id, project_id)


# ── Room Messages ─────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/rooms/{room_id}/messages", response_model=RoomMessageList)
async def list_room_messages(
    project_id: UUID,
    room_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    room_svc: RoomSvc,
    skip: int = Query(0, ge=0, description="Messages to skip"),
    limit: int = Query(50, ge=1, le=100, description="Max messages to return"),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    items, total = await room_svc.list_messages(room_id, project_id, skip=skip, limit=limit)
    return RoomMessageList(items=items, total=total)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/messages",
    response_model=RoomMessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_room_message(
    project_id: UUID,
    room_id: UUID,
    data: RoomMessageCreate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    room_svc: RoomSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    msg = await room_svc.create_message(room_id, project_id, data)
    # Broadcast to all WS clients in this room
    await room_hub.broadcast(str(room_id), {
        "type": "room_message",
        "id": str(msg.id),
        "sender": data.sender_name or user.email,
        "sender_type": data.sender_type,
        "message": data.content,
        "timestamp": msg.created_at.isoformat() if hasattr(msg.created_at, "isoformat") else str(msg.created_at),
    })
    return msg


# ── Room WebSocket ────────────────────────────────────────────────────────────


@router.websocket("/ws/rooms/{project_id}/{room_key}")
async def room_ws(
    websocket: WebSocket,
    project_id: UUID,
    room_key: str,
    user: Annotated[User, Depends(get_current_user_ws)],
) -> None:
    """Real-time room chat WebSocket.

    room_key can be a room UUID or the string "main" (auto-creates the main room).
    """
    subprotocol = getattr(websocket.state, "accept_subprotocol", None)
    await websocket.accept(subprotocol=subprotocol)

    async with get_db_context() as db:
        proj_svc = ProjectService(db)
        try:
            await proj_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
        except Exception:
            await websocket.close(code=4003, reason="Project not found or access denied")
            return

        room_svc = RoomService(db)

        # Resolve room: by UUID or by key ("main" → auto-create)
        room = None
        try:
            room_uuid = UUID(room_key)
            room = await room_svc.get(room_uuid, project_id)
        except (ValueError, Exception):
            # room_key is not a UUID — treat as a name slug, auto-create if needed
            items, _ = await room_svc.list(project_id, skip=0, limit=100)
            room = next((r for r in items if r.name.lower() == room_key.lower()), None)
            if room is None:
                from app.schemas.room import RoomCreate as _RC
                room = await room_svc.create(project_id, _RC(name=room_key.capitalize(), purpose="Main collaboration room"))

        room_id = str(room.id)
        project_id_str = str(project_id)

        # Send last 50 messages as history
        hist_items, _ = await room_svc.list_messages(room.id, project_id, skip=0, limit=50)

    # Subscribe to room-specific messages AND project-level agent broadcasts
    q = room_hub.join(room_id)
    project_q = room_hub.join(project_id_str)
    logger.info("Room WS joined: project=%s room=%s user=%s", project_id, room_id, user.email)

    try:
        await websocket.send_json({
            "type": "connected",
            "room_id": room_id,
            "room_name": room.name,
        })

        # Send history
        for h in hist_items:
            await websocket.send_json({
                "type": "history",
                "id": str(h.id),
                "sender": h.sender_name or str(h.sender_id or ""),
                "sender_type": h.sender_type,
                "message": h.content,
                "timestamp": h.created_at.isoformat() if hasattr(h.created_at, "isoformat") else str(h.created_at),
            })

        while True:
            try:
                # Wait for room broadcast, project-level agent event, or incoming message (25s ping)
                done, pending = await asyncio.wait(
                    [
                        asyncio.ensure_future(q.get()),
                        asyncio.ensure_future(project_q.get()),
                        asyncio.ensure_future(websocket.receive_json()),
                    ],
                    timeout=25.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for f in pending:
                    f.cancel()

                if not done:
                    # Timeout → ping
                    await websocket.send_json({"type": "ping"})
                    continue

                result = done.pop().result()

                # Result from broadcast queue → forward to client
                if isinstance(result, dict) and result.get("type") in (
                    "room_message", "agent_message", "agent_typing", "system",
                ):
                    await websocket.send_json(result)

                # Result from client (incoming message)
                elif isinstance(result, dict) and result.get("type") == "message":
                    content = str(result.get("content", "")).strip()
                    if not content:
                        continue
                    async with get_db_context() as db2:
                        room_svc2 = RoomService(db2)
                        from app.schemas.room import RoomMessageCreate as _RMC
                        msg = await room_svc2.create_message(
                            room.id,
                            project_id,
                            _RMC(
                                sender_type="user",
                                sender_id=user.id,
                                sender_name=user.email,
                                content=content,
                            ),
                        )
                    await room_hub.broadcast(room_id, {
                        "type": "room_message",
                        "id": str(msg.id),
                        "sender": user.email,
                        "sender_type": "user",
                        "message": content,
                        "timestamp": msg.created_at.isoformat() if hasattr(msg.created_at, "isoformat") else str(msg.created_at),
                    })

            except TimeoutError:
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        logger.info("Room WS left: project=%s room=%s user=%s", project_id, room_id, user.email)
    except Exception as exc:
        logger.exception("Room WS error: %s", exc)
    finally:
        room_hub.leave(room_id, q)
        room_hub.leave(project_id_str, project_q)
