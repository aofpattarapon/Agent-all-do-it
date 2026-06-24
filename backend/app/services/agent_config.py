"""AgentConfig service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.runtime_catalog import normalize_runtime_model_pair
from app.db.models.project import AgentConfig
from app.repositories import agent_config_repo
from app.schemas.agent_config import AgentConfigCreate, AgentConfigUpdate


def merge_runtime_tools_config(
    tools_config: dict[str, Any] | None,
    *,
    runtime_kind: str,
    model: str,
    fallback_chain: list[dict[str, str]] | None = None,
    gate_policy: str | None = None,
) -> dict[str, Any]:
    """Return ``tools_config`` with runtime/model fields synchronized.

    ``AgentConfig.runtime_kind`` and ``AgentConfig.model`` are the source of
    truth. The duplicated values in ``tools_config`` exist for older code
    paths and seeded data, so they must be rewritten whenever the agent
    runtime/model changes.

    When applying a runtime profile, pass ``fallback_chain`` and ``gate_policy``
    to persist them alongside the primary runtime settings.
    """
    merged = dict(tools_config or {})
    merged["runtime_kind"] = runtime_kind
    merged["ai_backend"] = runtime_kind
    merged["model"] = model
    if fallback_chain is not None:
        merged["fallback_chain"] = fallback_chain
    if gate_policy is not None:
        merged["gate_policy"] = gate_policy
    return merged


class AgentConfigService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, agent_id: UUID, project_id: UUID) -> AgentConfig:
        agent = await agent_config_repo.get_by_id(self.db, agent_id)
        if not agent or agent.project_id != project_id:
            raise NotFoundError(message="Agent not found", details={"agent_id": str(agent_id)})
        return agent

    async def list(
        self, project_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[list[AgentConfig], int]:
        return await agent_config_repo.list_by_project(
            self.db, project_id=project_id, skip=skip, limit=limit
        )

    async def create(self, project_id: UUID, data: AgentConfigCreate) -> AgentConfig:
        runtime_kind, model = normalize_runtime_model_pair(data.runtime_kind, data.model)
        tools_config = merge_runtime_tools_config(
            data.tools_config,
            runtime_kind=runtime_kind,
            model=model,
        )
        return await agent_config_repo.create(
            self.db,
            project_id=project_id,
            name=data.name,
            role=data.role,
            system_prompt=data.system_prompt,
            tools_config=tools_config,
            order_index=data.order_index,
            avatar=data.avatar,
            runtime_kind=runtime_kind,
            model=model,
            working_directory=data.working_directory,
            tool_permissions=data.tool_permissions,
            max_tokens=data.max_tokens,
            temperature=data.temperature,
            memory_type=data.memory_type,
            context_window_size=data.context_window_size,
        )

    async def update(
        self, agent_id: UUID, project_id: UUID, data: AgentConfigUpdate
    ) -> AgentConfig:
        agent = await self.get(agent_id, project_id)
        update_data = data.model_dump(exclude_unset=True)
        runtime_kind = update_data.get("runtime_kind", agent.runtime_kind)
        model = update_data.get("model", agent.model)
        runtime_kind, model = normalize_runtime_model_pair(runtime_kind, model)
        update_data["runtime_kind"] = runtime_kind
        update_data["model"] = model
        tools_config_input = agent.tools_config
        if isinstance(update_data.get("tools_config"), dict):
            tools_config_input = {
                **dict(agent.tools_config or {}),
                **update_data["tools_config"],
            }
        update_data["tools_config"] = merge_runtime_tools_config(
            tools_config_input,
            runtime_kind=runtime_kind,
            model=model,
        )
        return await agent_config_repo.update(self.db, db_agent=agent, update_data=update_data)

    async def delete(self, agent_id: UUID, project_id: UUID) -> None:
        agent = await self.get(agent_id, project_id)
        await agent_config_repo.delete(self.db, agent.id)
