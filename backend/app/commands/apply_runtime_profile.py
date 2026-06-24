"""Apply a runtime profile to all agents in a project.

Switches all 12 crypto agents between named runtime profiles in one command.

Usage:
    uv run pixel_dream_agent cmd apply-runtime-profile --project-id <uuid> --profile test --dry-run
    uv run pixel_dream_agent cmd apply-runtime-profile --project-id <uuid> --profile test-2 --dry-run
    uv run pixel_dream_agent cmd apply-runtime-profile --project-id <uuid> --profile test-minimal-paid --dry-run
    uv run pixel_dream_agent cmd apply-runtime-profile --project-id <uuid> --profile test-local-free-24x7-safe --dry-run
    uv run pixel_dream_agent cmd apply-runtime-profile --project-id <uuid> --profile production
"""

import asyncio
from uuid import UUID

import click
from sqlalchemy import select

from app.commands import command, error, info, success, warning
from app.core.runtime_catalog import normalize_runtime_model_pair
from app.db.models.project import AgentConfig
from app.db.session import get_db_context
from app.services.agent_config import merge_runtime_tools_config
from app.services.runtime_profiles import VALID_PROFILES, get_profile


def _format_fallback_chain(fallback_chain: list[dict[str, str]]) -> str:
    if not fallback_chain:
        return "none"
    return " -> ".join(
        f"{entry.get('runtime_kind', '-')}/{entry.get('model', '-')}" for entry in fallback_chain
    )


@command(
    "apply-runtime-profile",
    help="Apply a runtime profile to all agents in a project",
)
@click.option("--project-id", type=str, required=True, help="Target project UUID")
@click.option(
    "--profile",
    type=click.Choice(list(VALID_PROFILES)),
    required=True,
    help="Profile name",
)
@click.option("--dry-run", is_flag=True, help="Show planned changes without saving")
def apply_runtime_profile(project_id: str, profile: str, dry_run: bool) -> None:
    """Apply a named runtime profile to every agent in the given project."""
    try:
        target_project_id = UUID(project_id)
    except ValueError:
        error(f"Invalid project-id: '{project_id}' is not a valid UUID.")
        return

    profile_map = get_profile(profile)

    async def _run() -> None:
        async with get_db_context() as db:
            query = (
                select(AgentConfig)
                .where(AgentConfig.project_id == target_project_id)
                .order_by(AgentConfig.order_index, AgentConfig.name)
            )
            rows = await db.execute(query)
            agents = list(rows.scalars().all())

            if not agents:
                warning(f"No agents found for project {project_id}.")
                return

            changed = 0
            skipped = 0

            for agent in agents:
                role = getattr(agent, "role", None) or ""
                policy = profile_map.get(role)

                if policy is None:
                    warning(
                        f"  {agent.name} (role={role!r}): no mapping in '{profile}' profile — skipped"
                    )
                    skipped += 1
                    continue

                runtime_kind, model = normalize_runtime_model_pair(
                    policy["runtime_kind"], policy["model"]
                )
                fallback_chain = policy.get("fallback_chain", [])
                gate_policy = policy.get("gate_policy", "continue")
                temperature = policy.get("temperature")
                max_tokens = policy.get("max_tokens")

                next_tools = merge_runtime_tools_config(
                    agent.tools_config,
                    runtime_kind=runtime_kind,
                    model=model,
                    fallback_chain=fallback_chain,
                    gate_policy=gate_policy,
                )

                needs_change = (
                    agent.runtime_kind != runtime_kind
                    or agent.model != model
                    or dict(agent.tools_config or {}).get("fallback_chain") != fallback_chain
                    or dict(agent.tools_config or {}).get("gate_policy") != gate_policy
                    or (temperature is not None and agent.temperature != temperature)
                    or (max_tokens is not None and agent.max_tokens != max_tokens)
                )

                if not needs_change:
                    info(f"  {agent.name}: already on '{profile}' profile — no change")
                    continue

                changed += 1
                info(
                    f"  {agent.name} (role={role!r}): "
                    f"{agent.runtime_kind or '-'}/{agent.model or '-'} "
                    f"→ {runtime_kind}/{model} "
                    f"[gate={gate_policy}, fallbacks={_format_fallback_chain(fallback_chain)}]"
                )

                if dry_run:
                    continue

                agent.runtime_kind = runtime_kind
                agent.model = model
                agent.tools_config = next_tools
                if temperature is not None:
                    agent.temperature = temperature
                if max_tokens is not None:
                    agent.max_tokens = max_tokens
                db.add(agent)

            if dry_run:
                success(
                    f"\nDry run complete. "
                    f"{changed} agent(s) would be updated, {skipped} skipped (no role mapping)."
                )
                return

            # Persist active profile in app_settings for UI visibility.
            from sqlalchemy import text

            setting_key = f"project.{project_id}.runtime_profile"
            await db.execute(
                text(
                    "INSERT INTO app_settings (key, value, description) VALUES (:key, :value, :desc) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
                ),
                {
                    "key": setting_key,
                    "value": profile,
                    "desc": f"Active runtime profile for project {project_id}",
                },
            )

            await db.commit()
            success(
                f"\nApplied '{profile}' profile. "
                f"{changed} agent(s) updated, {skipped} skipped (no role mapping)."
            )

    asyncio.run(_run())
