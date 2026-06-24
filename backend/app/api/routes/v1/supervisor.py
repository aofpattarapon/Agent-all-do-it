"""Supervisor route — queue project-agent supervisor runs in the background."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from app.api.deps import AgentConfigSvc, AppSettingSvc, CurrentUser, ProjectSvc, RunSvc
from app.core.exceptions import ValidationError
from app.core.rbac import Permission
from app.core.runtime_catalog import normalize_runtime_model_pair
from app.db.session import get_db_context
from app.schemas.run import RunCreate, RunUpdate
from app.services.agent_config import AgentConfigService
from app.services.app_setting import AppSettingService
from app.services.event_bus import AgentEvent, event_bus
from app.services.run import RunService

router = APIRouter()


class RunTaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=10000)
    agent_id: UUID | None = None
    agent_ids: list[UUID] | None = None


class RunTaskResponse(BaseModel):
    id: UUID
    project_id: UUID
    task: str
    status: str
    queued: bool = True
    result: str = ""
    agents_used: list[str]
    backend_used: str


def _is_error_result(text: str) -> bool:
    prefixes = (
        "[Agent error:",
        "[kimi-cli error",
        "[claude-cli error",
        "[codex-cli error",
    )
    return text.startswith(prefixes)


def _summarize_backend(active: list[dict[str, Any]], fallback: str) -> str:
    runtimes = {
        str((agent.get("tools_config") or {}).get("runtime_kind") or fallback) for agent in active
    }
    if not runtimes:
        return fallback
    if len(runtimes) == 1:
        return next(iter(runtimes))
    return "mixed"


async def _load_active_agents(
    project_id: UUID,
    agent_svc: AgentConfigService,
    setting_svc: AppSettingService,
    selected_agent_id: UUID | None = None,
    selected_agent_ids: list[UUID] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    global_cfg = await setting_svc.get_ai_config()
    agents, _ = await agent_svc.list(project_id, limit=50)
    active: list[dict[str, Any]] = []
    ordered_selection = [str(agent_id) for agent_id in (selected_agent_ids or [])]
    selected_id_set = set(ordered_selection)
    selected_active: dict[str, dict[str, Any]] = {}

    for a in agents:
        if not a.is_active:
            continue
        if ordered_selection and str(a.id) not in selected_id_set:
            continue
        if not ordered_selection and selected_agent_id is not None and a.id != selected_agent_id:
            continue
        per_agent = dict(a.tools_config) if a.tools_config else {}
        runtime_candidate = (
            a.runtime_kind
            or per_agent.get("runtime_kind")
            or per_agent.get("ai_backend")
            or global_cfg["default_backend"]
        )
        model_candidate = a.model or per_agent.get("model") or global_cfg["default_model"]
        try:
            runtime_kind, model = normalize_runtime_model_pair(
                runtime_candidate,
                model_candidate,
            )
        except ValidationError:
            runtime_kind, model = normalize_runtime_model_pair(runtime_candidate, "")

        merged_cfg = {
            "ai_backend": runtime_kind,
            "runtime_kind": runtime_kind,
            "model": model,
            "auto_fallback": per_agent.get("auto_fallback", global_cfg["auto_fallback"]),
            "_anthropic_api_key": global_cfg["anthropic_api_key"],
        }
        payload = {
            "id": str(a.id),
            "name": a.name,
            "role": a.role,
            "system_prompt": a.system_prompt,
            "is_active": a.is_active,
            "tools_config": merged_cfg,
            "max_tokens": getattr(a, "max_tokens", 2048),
            "temperature": getattr(a, "temperature", 70),
        }
        if ordered_selection:
            selected_active[str(a.id)] = payload
        else:
            active.append(payload)

    if ordered_selection:
        active = [
            selected_active[agent_id]
            for agent_id in ordered_selection
            if agent_id in selected_active
        ]

    return active, global_cfg


async def _execute_supervisor_bg(
    *,
    run_id: UUID,
    project_id: UUID,
    task: str,
    selected_agent_id: UUID | None,
    selected_agent_ids: list[UUID] | None,
) -> None:
    async with get_db_context() as db:
        run_svc = RunService(db)
        agent_svc = AgentConfigService(db)
        setting_svc = AppSettingService(db)
        await run_svc.get(run_id, project_id)

        active, global_cfg = await _load_active_agents(
            project_id,
            agent_svc,
            setting_svc,
            selected_agent_id=selected_agent_id,
            selected_agent_ids=selected_agent_ids,
        )

        if not active:
            await run_svc.update(
                run_id,
                project_id,
                RunUpdate(
                    status="failed",
                    error_text="No active agents configured for this project.",
                ),
            )
            await event_bus.emit(
                AgentEvent(
                    type="run.failed",
                    project_id=str(project_id),
                    run_id=str(run_id),
                    task=task,
                    data="No active agents configured for this project.",
                )
            )
            return

        backend_used = _summarize_backend(active, global_cfg["default_backend"])
        await run_svc.update(
            run_id,
            project_id,
            RunUpdate(
                status="running",
                started_at=datetime.now(UTC),
                runtime_summary={
                    "mode": "supervisor",
                    "agent_count": len(active),
                    "backend_used": backend_used,
                    "agent_ids": [a["id"] for a in active],
                },
            ),
        )
        await run_svc.db.commit()
        await event_bus.emit(
            AgentEvent(
                type="task_started",
                project_id=str(project_id),
                run_id=str(run_id),
                task=task,
                data=f"{len(active)} agents queued",
            )
        )

        from app.agents.supervisor import SupervisorAgent

        try:
            supervisor = SupervisorAgent(agent_configs=active, run_id=str(run_id))
            result = await supervisor.run(task=task, project_id=str(project_id))
            failed = _is_error_result(result)
            status_value = "failed" if failed else "completed"
            await run_svc.update(
                run_id,
                project_id,
                RunUpdate(
                    status=status_value,
                    output_text=result if not failed else "",
                    error_text=result if failed else "",
                    finished_at=datetime.now(UTC),
                    runtime_summary={
                        "mode": "supervisor",
                        "agent_count": len(active),
                        "backend_used": backend_used,
                        "agent_ids": [a["id"] for a in active],
                        "agents_used": [a["name"] for a in active],
                    },
                ),
            )
            await run_svc.db.commit()
            await event_bus.emit(
                AgentEvent(
                    type="task_done" if not failed else "run.failed",
                    project_id=str(project_id),
                    run_id=str(run_id),
                    task=task,
                    data=result[:1000],
                )
            )
            if not failed:
                await event_bus.emit(
                    AgentEvent(
                        type="run.completed",
                        project_id=str(project_id),
                        run_id=str(run_id),
                        task=task,
                        data=result[:1000],
                    )
                )
        except Exception as exc:
            message = f"[Agent error: {exc}]"
            await run_svc.update(
                run_id,
                project_id,
                RunUpdate(
                    status="failed",
                    error_text=message,
                    finished_at=datetime.now(UTC),
                    runtime_summary={
                        "mode": "supervisor",
                        "agent_count": len(active),
                        "backend_used": backend_used,
                        "agent_ids": [a["id"] for a in active],
                        "agents_used": [a["name"] for a in active],
                    },
                ),
            )
            await run_svc.db.commit()
            await event_bus.emit(
                AgentEvent(
                    type="run.failed",
                    project_id=str(project_id),
                    run_id=str(run_id),
                    task=task,
                    data=message[:1000],
                )
            )


@router.post("/projects/{project_id}/run", response_model=RunTaskResponse)
async def run_project(
    project_id: UUID,
    body: RunTaskRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    project_svc: ProjectSvc,
    agent_svc: AgentConfigSvc,
    setting_svc: AppSettingSvc,
    run_svc: RunSvc,
) -> Any:
    """Queue a background supervisor run and return immediately."""
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_EXECUTE)
    if body.agent_id is not None:
        await agent_svc.get(body.agent_id, project_id)
    if body.agent_ids:
        for agent_id in body.agent_ids:
            await agent_svc.get(agent_id, project_id)

    active, global_cfg = await _load_active_agents(
        project_id,
        agent_svc,
        setting_svc,
        selected_agent_id=body.agent_id,
        selected_agent_ids=body.agent_ids,
    )
    backend_used = _summarize_backend(active, global_cfg["default_backend"])
    run = await run_svc.create(
        project_id,
        RunCreate(
            trigger="manual_supervisor",
            input_payload_json={
                "task": body.task,
                "mode": "supervisor",
                "agent_id": str(body.agent_id) if body.agent_id else None,
                "agent_ids": [str(agent_id) for agent_id in (body.agent_ids or [])],
            },
        ),
    )
    await run_svc.db.commit()
    await run_svc.db.refresh(run)
    if not active:
        await run_svc.update(
            run.id,
            project_id,
            RunUpdate(
                status="failed",
                error_text="No active agents configured for this project.",
            ),
        )
        await run_svc.db.commit()
        await run_svc.db.refresh(run)
        return RunTaskResponse(
            id=run.id,
            project_id=project_id,
            task=body.task,
            status="failed",
            result="No active agents configured for this project.",
            agents_used=[],
            backend_used="none",
        )

    background_tasks.add_task(
        _execute_supervisor_bg,
        run_id=run.id,
        project_id=project_id,
        task=body.task,
        selected_agent_id=body.agent_id,
        selected_agent_ids=body.agent_ids,
    )
    return RunTaskResponse(
        id=run.id,
        project_id=project_id,
        task=body.task,
        status="queued",
        result="",
        agents_used=[a["name"] for a in active],
        backend_used=backend_used,
    )
