"""AgentConfig repository."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import AgentConfig


async def get_by_id(db: AsyncSession, agent_id: UUID) -> AgentConfig | None:
    return await db.get(AgentConfig, agent_id)


async def list_by_project(
    db: AsyncSession, *, project_id: UUID, skip: int = 0, limit: int = 100
) -> tuple[list[AgentConfig], int]:
    query = (
        select(AgentConfig)
        .where(AgentConfig.project_id == project_id)
        .order_by(AgentConfig.order_index.asc())
    )
    count_query = select(func.count()).select_from(AgentConfig).where(AgentConfig.project_id == project_id)
    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all()), total


async def create(
    db: AsyncSession,
    *,
    project_id: UUID,
    name: str,
    role: str,
    system_prompt: str,
    tools_config: dict,
    order_index: int = 0,
    **extra: Any,
) -> AgentConfig:
    agent = AgentConfig(
        project_id=project_id,
        name=name,
        role=role,
        system_prompt=system_prompt,
        tools_config=tools_config,
        order_index=order_index,
        **extra,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def update(db: AsyncSession, *, db_agent: AgentConfig, update_data: dict[str, Any]) -> AgentConfig:
    for field, value in update_data.items():
        setattr(db_agent, field, value)
    db.add(db_agent)
    await db.flush()
    await db.refresh(db_agent)
    return db_agent


async def delete(db: AsyncSession, agent_id: UUID) -> AgentConfig | None:
    agent = await get_by_id(db, agent_id)
    if agent:
        await db.delete(agent)
        await db.flush()
    return agent
