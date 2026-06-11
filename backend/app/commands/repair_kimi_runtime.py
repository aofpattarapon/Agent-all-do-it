"""Repair agent runtime/model settings and optionally switch them to Kimi CLI."""

import asyncio
from uuid import UUID

import click
from sqlalchemy import select

from app.commands import command, info, success, warning
from app.core.runtime_catalog import normalize_runtime_model_pair
from app.db.models.project import AgentConfig
from app.db.session import get_db_context
from app.services.agent_config import merge_runtime_tools_config


@command("repair-kimi-runtime", help="Normalize agent runtime fields and switch agents to kimi-cli/kimi-k2.6")
@click.option("--project-id", type=str, help="Only repair agents in the given project")
@click.option("--runtime", default="kimi-cli", show_default=True, help="Target runtime kind")
@click.option("--model", default="kimi-k2.6", show_default=True, help="Target model")
@click.option("--dry-run", is_flag=True, help="Show planned changes without saving")
def repair_kimi_runtime(
    project_id: str | None,
    runtime: str,
    model: str,
    dry_run: bool,
) -> None:
    """Synchronize runtime/model fields and switch targeted agents to Kimi CLI."""
    normalized_runtime, normalized_model = normalize_runtime_model_pair(runtime, model)
    target_project_id = UUID(project_id) if project_id else None

    async def _run() -> None:
        async with get_db_context() as db:
            query = select(AgentConfig).order_by(AgentConfig.project_id, AgentConfig.order_index, AgentConfig.name)
            if target_project_id is not None:
                query = query.where(AgentConfig.project_id == target_project_id)
            rows = await db.execute(query)
            agents = list(rows.scalars().all())

            if not agents:
                warning("No agents matched the requested scope.")
                return

            changed = 0
            for agent in agents:
                next_tools = merge_runtime_tools_config(
                    agent.tools_config,
                    runtime_kind=normalized_runtime,
                    model=normalized_model,
                )
                needs_change = (
                    agent.runtime_kind != normalized_runtime
                    or agent.model != normalized_model
                    or dict(agent.tools_config or {}) != next_tools
                )
                if not needs_change:
                    continue

                changed += 1
                info(
                    f"{agent.name}: "
                    f"{agent.runtime_kind or '-'} / {agent.model or '-'} -> "
                    f"{normalized_runtime} / {normalized_model}"
                )
                if dry_run:
                    continue
                agent.runtime_kind = normalized_runtime
                agent.model = normalized_model
                agent.tools_config = next_tools
                db.add(agent)

            if dry_run:
                success(f"Dry run complete. {changed} agent(s) would be updated.")
                return

            await db.commit()
            success(f"Updated {changed} agent(s) to {normalized_runtime} / {normalized_model}.")

    asyncio.run(_run())
