"""Room service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.room import Room, RoomMessage
from app.repositories import room_repo
from app.schemas.room import RoomCreate, RoomMessageCreate, RoomUpdate


class RoomService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, room_id: UUID, project_id: UUID) -> Room:
        room = await room_repo.get_room_by_id(self.db, room_id)
        if not room or room.project_id != project_id:
            raise NotFoundError(message="Room not found", details={"room_id": str(room_id)})
        return room

    async def list(
        self, project_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[list[Room], int]:
        return await room_repo.list_rooms_by_project(
            self.db, project_id=project_id, skip=skip, limit=limit
        )

    async def create(self, project_id: UUID, data: RoomCreate) -> Room:
        return await room_repo.create_room(
            self.db,
            project_id=project_id,
            name=data.name,
            purpose=data.purpose,
        )

    async def update(self, room_id: UUID, project_id: UUID, data: RoomUpdate) -> Room:
        room = await self.get(room_id, project_id)
        update_data = data.model_dump(exclude_unset=True)
        return await room_repo.update_room(self.db, db_room=room, update_data=update_data)

    async def delete(self, room_id: UUID, project_id: UUID) -> None:
        room = await self.get(room_id, project_id)
        await room_repo.delete_room(self.db, room.id)

    # ── Messages ──────────────────────────────────────────────────────────────

    async def list_messages(
        self, room_id: UUID, project_id: UUID, skip: int = 0, limit: int = 50
    ) -> tuple[list[RoomMessage], int]:
        await self.get(room_id, project_id)  # ownership check
        return await room_repo.list_messages_by_room(
            self.db, room_id=room_id, skip=skip, limit=limit
        )

    async def create_message(
        self, room_id: UUID, project_id: UUID, data: RoomMessageCreate
    ) -> RoomMessage:
        await self.get(room_id, project_id)  # ownership check
        return await room_repo.create_room_message(
            self.db,
            room_id=room_id,
            sender_type=data.sender_type,
            content=data.content,
            sender_id=data.sender_id,
            sender_name=data.sender_name,
            metadata_json=data.metadata_json,
        )
