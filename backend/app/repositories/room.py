"""Room and RoomMessage repositories."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.room import Room, RoomMessage


# ── Room ──────────────────────────────────────────────────────────────────────


async def get_room_by_id(db: AsyncSession, room_id: UUID) -> Room | None:
    return await db.get(Room, room_id)


async def list_rooms_by_project(
    db: AsyncSession, *, project_id: UUID, skip: int = 0, limit: int = 100
) -> tuple[list[Room], int]:
    query = (
        select(Room)
        .where(Room.project_id == project_id)
        .order_by(Room.created_at.asc())
    )
    count_query = select(func.count()).select_from(Room).where(Room.project_id == project_id)
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create_room(
    db: AsyncSession,
    *,
    project_id: UUID,
    name: str,
    purpose: str = "",
) -> Room:
    room = Room(
        project_id=project_id,
        name=name,
        purpose=purpose,
    )
    db.add(room)
    await db.flush()
    await db.refresh(room)
    return room


async def update_room(db: AsyncSession, *, db_room: Room, update_data: dict[str, Any]) -> Room:
    for field, value in update_data.items():
        setattr(db_room, field, value)
    db.add(db_room)
    await db.flush()
    await db.refresh(db_room)
    return db_room


async def delete_room(db: AsyncSession, room_id: UUID) -> Room | None:
    room = await get_room_by_id(db, room_id)
    if room:
        await db.delete(room)
        await db.flush()
    return room


# ── RoomMessage ───────────────────────────────────────────────────────────────


async def list_messages_by_room(
    db: AsyncSession, *, room_id: UUID, skip: int = 0, limit: int = 50
) -> tuple[list[RoomMessage], int]:
    query = (
        select(RoomMessage)
        .where(RoomMessage.room_id == room_id)
        .order_by(RoomMessage.created_at.asc())
    )
    count_query = select(func.count()).select_from(RoomMessage).where(RoomMessage.room_id == room_id)
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create_room_message(
    db: AsyncSession,
    *,
    room_id: UUID,
    sender_type: str,
    content: str,
    sender_id: UUID | None = None,
    sender_name: str = "",
    metadata_json: dict | None = None,
) -> RoomMessage:
    message = RoomMessage(
        room_id=room_id,
        sender_type=sender_type,
        content=content,
        sender_id=sender_id,
        sender_name=sender_name,
        metadata_json=metadata_json or {},
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message
