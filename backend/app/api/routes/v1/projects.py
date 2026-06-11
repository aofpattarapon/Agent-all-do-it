"""Projects, AgentConfig, AgentChat, and per-agent knowledge routes."""

from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile, status
from pydantic import BaseModel

from app.api.deps import AgentChatSvc, AgentConfigSvc, AppSettingSvc, CurrentUser, DBSession, KnowledgeSvc, ProjectSvc
from app.core.rbac import Permission
from app.schemas.agent_chat import AgentChatRequest, AgentChatResponse
from app.schemas.agent_config import (
    AgentConfigCreate,
    AgentConfigList,
    AgentConfigRead,
    AgentConfigUpdate,
)
from app.schemas.knowledge import (
    KnowledgeDocCreate,
    KnowledgeDocList,
    KnowledgeDocRead,
    KnowledgeDocUpdate,
)
from app.schemas.project import ProjectCreate, ProjectList, ProjectRead, ProjectUpdate

router = APIRouter()

# ── Vault path helper ─────────────────────────────────────────────────────────

VAULT_BASE = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "vaults"


def get_project_vault_path(project_id: UUID) -> Path:
    vault_dir = VAULT_BASE / str(project_id)
    vault_dir.mkdir(parents=True, exist_ok=True)
    return vault_dir


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/projects", response_model=ProjectList)
async def list_projects(
    user: CurrentUser, svc: ProjectSvc,
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
) -> Any:
    items, total = await svc.list(user.id, skip=skip, limit=limit)
    return ProjectList(items=items, total=total)


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, user: CurrentUser, svc: ProjectSvc) -> Any:
    return await svc.create(user.id, data)


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: UUID, user: CurrentUser, svc: ProjectSvc) -> Any:
    access = await svc.resolve_access(
        project_id, user, require=Permission.PROJECT_VIEW
    )
    return access.project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
async def update_project(project_id: UUID, data: ProjectUpdate, user: CurrentUser, svc: ProjectSvc) -> Any:
    await svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)
    return await svc.update(project_id, user.id, data)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_project(project_id: UUID, user: CurrentUser, svc: ProjectSvc) -> None:
    await svc.resolve_access(project_id, user, require=Permission.PROJECT_DELETE)
    await svc.delete(project_id, user.id)


# ── Runtime profiles ──────────────────────────────────────────────────────────

class RuntimeProfileRead(BaseModel):
    profile: str | None
    valid_profiles: list[str]


class RuntimeProfileApply(BaseModel):
    profile: Literal["test", "production"]


@router.get("/projects/{project_id}/runtime-profile", response_model=RuntimeProfileRead)
async def get_runtime_profile(
    project_id: UUID, user: CurrentUser, project_svc: ProjectSvc, settings_svc: AppSettingSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_VIEW)
    from app.services.runtime_profiles import VALID_PROFILES
    key = f"project.{project_id}.runtime_profile"
    active = await settings_svc.get(key, default="")
    return RuntimeProfileRead(
        profile=active or None,
        valid_profiles=list(VALID_PROFILES),
    )


@router.post("/projects/{project_id}/runtime-profile", response_model=RuntimeProfileRead)
async def apply_runtime_profile(
    project_id: UUID,
    body: RuntimeProfileApply,
    user: CurrentUser,
    project_svc: ProjectSvc,
    agent_svc: AgentConfigSvc,
    settings_svc: AppSettingSvc,
    db: DBSession,
) -> Any:
    from app.core.runtime_catalog import normalize_runtime_model_pair
    from app.services.agent_config import merge_runtime_tools_config
    from app.services.runtime_profiles import VALID_PROFILES, get_profile

    await project_svc.resolve_access(project_id, user, require=Permission.PROJECT_EDIT)

    profile_map = get_profile(body.profile)
    agents, _ = await agent_svc.list(project_id, skip=0, limit=200)

    for agent in agents:
        role = getattr(agent, "role", None) or ""
        policy = profile_map.get(role)
        if policy is None:
            continue

        runtime_kind, model = normalize_runtime_model_pair(policy["runtime_kind"], policy["model"])
        agent.runtime_kind = runtime_kind
        agent.model = model
        agent.tools_config = merge_runtime_tools_config(
            agent.tools_config,
            runtime_kind=runtime_kind,
            model=model,
            fallback_chain=policy.get("fallback_chain", []),
            gate_policy=policy.get("gate_policy", "continue"),
        )
        db.add(agent)

    await db.flush()
    await settings_svc.set(f"project.{project_id}.runtime_profile", body.profile)

    return RuntimeProfileRead(profile=body.profile, valid_profiles=list(VALID_PROFILES))


# ── AgentConfigs ──────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/agents", response_model=AgentConfigList)
async def list_agents(
    project_id: UUID, user: CurrentUser, project_svc: ProjectSvc, agent_svc: AgentConfigSvc,
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.AGENT_VIEW)
    items, total = await agent_svc.list(project_id, skip=skip, limit=limit)
    return AgentConfigList(items=items, total=total)


@router.post("/projects/{project_id}/agents", response_model=AgentConfigRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    project_id: UUID, data: AgentConfigCreate, user: CurrentUser,
    project_svc: ProjectSvc, agent_svc: AgentConfigSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.AGENT_EDIT)
    return await agent_svc.create(project_id, data)


@router.patch("/projects/{project_id}/agents/{agent_id}", response_model=AgentConfigRead)
async def update_agent(
    project_id: UUID, agent_id: UUID, data: AgentConfigUpdate, user: CurrentUser,
    project_svc: ProjectSvc, agent_svc: AgentConfigSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.AGENT_EDIT)
    return await agent_svc.update(agent_id, project_id, data)


@router.delete("/projects/{project_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_agent(
    project_id: UUID, agent_id: UUID, user: CurrentUser,
    project_svc: ProjectSvc, agent_svc: AgentConfigSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.AGENT_EDIT)
    await agent_svc.delete(agent_id, project_id)


# ── Agent Direct Chat ─────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/agents/{agent_id}/chat", response_model=AgentChatResponse)
async def chat_with_agent(
    project_id: UUID, agent_id: UUID,
    data: AgentChatRequest, user: CurrentUser,
    project_svc: ProjectSvc, chat_svc: AgentChatSvc,
) -> Any:
    """Send a direct message to a specific agent and get a response."""
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_EXECUTE)
    return await chat_svc.chat(
        agent_config_id=agent_id,
        project_id=project_id,
        message=data.message,
        include_knowledge=data.include_knowledge,
    )


# ── Per-Agent Knowledge ───────────────────────────────────────────────────────

@router.get("/projects/{project_id}/agents/{agent_id}/knowledge", response_model=KnowledgeDocList)
async def list_agent_knowledge(
    project_id: UUID, agent_id: UUID, user: CurrentUser,
    project_svc: ProjectSvc, knowledge_svc: KnowledgeSvc,
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_VIEW)
    items, total = await knowledge_svc.list_by_agent(agent_id, project_id, skip=skip, limit=limit)
    return KnowledgeDocList(items=items, total=total)


@router.post(
    "/projects/{project_id}/agents/{agent_id}/knowledge",
    response_model=KnowledgeDocRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_knowledge(
    project_id: UUID, agent_id: UUID, data: KnowledgeDocCreate,
    user: CurrentUser, project_svc: ProjectSvc, knowledge_svc: KnowledgeSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)
    return await knowledge_svc.create(project_id, data, agent_config_id=agent_id)


@router.post(
    "/projects/{project_id}/agents/{agent_id}/knowledge/upload",
    response_model=KnowledgeDocRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_agent_knowledge(
    project_id: UUID, agent_id: UUID,
    file: UploadFile = File(...),
    user: CurrentUser = ...,
    project_svc: ProjectSvc = ...,
    knowledge_svc: KnowledgeSvc = ...,
) -> Any:
    """Upload a .md file as agent knowledge."""
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)
    content_bytes = await file.read()
    content = content_bytes.decode("utf-8", errors="replace")

    # Extract title from first H1 heading or filename
    title = Path(file.filename or "document.md").stem
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break

    data = KnowledgeDocCreate(
        title=title,
        content=content,
        tags=[],
        source_url=file.filename,
        agent_config_id=agent_id,
        source_type="upload",
    )
    return await knowledge_svc.create(project_id, data, agent_config_id=agent_id)


# ── Project-level Knowledge (existing) ───────────────────────────────────────

@router.get("/projects/{project_id}/knowledge", response_model=KnowledgeDocList)
async def list_knowledge(
    project_id: UUID, user: CurrentUser, project_svc: ProjectSvc, knowledge_svc: KnowledgeSvc,
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_VIEW)
    items, total = await knowledge_svc.list(project_id, skip=skip, limit=limit, search=search)
    return KnowledgeDocList(items=items, total=total)


@router.post("/projects/{project_id}/knowledge", response_model=KnowledgeDocRead, status_code=status.HTTP_201_CREATED)
async def create_knowledge(
    project_id: UUID, data: KnowledgeDocCreate, user: CurrentUser,
    project_svc: ProjectSvc, knowledge_svc: KnowledgeSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)
    return await knowledge_svc.create(project_id, data)


@router.post(
    "/projects/{project_id}/knowledge/upload",
    response_model=KnowledgeDocRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_knowledge_file(
    project_id: UUID,
    file: UploadFile = File(...),
    user: CurrentUser = ...,
    project_svc: ProjectSvc = ...,
    knowledge_svc: KnowledgeSvc = ...,
) -> Any:
    """Upload a .md file to project knowledge base."""
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)
    content_bytes = await file.read()
    content = content_bytes.decode("utf-8", errors="replace")
    title = Path(file.filename or "document.md").stem
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break
    data = KnowledgeDocCreate(title=title, content=content, tags=[], source_url=file.filename, source_type="upload")
    return await knowledge_svc.create(project_id, data)


@router.patch("/projects/{project_id}/knowledge/{doc_id}", response_model=KnowledgeDocRead)
async def update_knowledge(
    project_id: UUID, doc_id: UUID, data: KnowledgeDocUpdate, user: CurrentUser,
    project_svc: ProjectSvc, knowledge_svc: KnowledgeSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)
    return await knowledge_svc.update(doc_id, project_id, data)


@router.delete("/projects/{project_id}/knowledge/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_knowledge(
    project_id: UUID, doc_id: UUID, user: CurrentUser,
    project_svc: ProjectSvc, knowledge_svc: KnowledgeSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)
    await knowledge_svc.delete(doc_id, project_id)


# ── Obsidian Vault Sync ───────────────────────────────────────────────────────

@router.post("/projects/{project_id}/vault/sync")
async def sync_obsidian_vault(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    knowledge_svc: KnowledgeSvc,
    agent_id: UUID | None = Query(None),
) -> Any:
    """Sync .md files from the project-local vault directory into the project knowledge base."""
    await project_svc.resolve_access(project_id, user, require=Permission.KNOWLEDGE_EDIT)

    vault = get_project_vault_path(project_id)
    if not vault.is_dir():
        return {"error": f"Vault directory not found: {vault}", "synced": 0, "updated": 0}

    synced, updated, errors = 0, 0, []
    for md_file in vault.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
            title = md_file.stem
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    title = stripped[2:].strip()
                    break
            file_url = str(md_file)
            result = await knowledge_svc.upsert_by_source_url(
                project_id=project_id,
                source_url=file_url,
                title=title,
                content=content,
                source_type="obsidian",
                agent_config_id=agent_id,
            )
            if result[1]:  # (doc, was_created)
                synced += 1
            else:
                updated += 1
        except Exception as exc:
            errors.append({"file": str(md_file), "error": str(exc)})

    return {"synced": synced, "updated": updated, "errors": errors[:10]}
