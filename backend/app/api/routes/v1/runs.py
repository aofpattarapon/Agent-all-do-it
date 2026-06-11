"""Run routes."""

import asyncio
import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse

from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, ProjectSvc, RunSvc
from app.db.models.workflow import Run, RunStep, Workflow
from app.core.rate_limit import limiter
from app.core.rbac import Permission
from app.repositories import run as run_repo
from app.schemas.run import RunCreate, RunList, RunRead, RunStepList, RunUpdate
from app.services.run_executor import RunExecutor

logger = logging.getLogger(__name__)
router = APIRouter()


def _dispatch_task(task_name: str, *args: str) -> str:
    """Publish a Celery task explicitly by name via a short-lived subprocess.

    The request process has shown inconsistent producer behavior while the same
    publish path works reliably from a separate Python process inside the same
    container. Use the known-good subprocess path until the root cause is
    narrowed further.
    """
    code = (
        "import sys\n"
        "from app.worker.celery_app import celery_app\n"
        "res = celery_app.send_task(sys.argv[1], args=sys.argv[2:])\n"
        "print(res.id)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, task_name, *args],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    task_id = proc.stdout.strip().splitlines()[-1].strip()
    if not task_id:
        raise RuntimeError(f"Failed to dispatch Celery task {task_name}: no task id returned")
    logger.info("Dispatched Celery task %s id=%s args=%s", task_name, task_id, args)
    return task_id


def _to_run_read(run: Any, workflow_name: str | None = None) -> RunRead:
    """Convert an ORM run instance to a concrete response DTO inside the request context."""
    return RunRead(
        id=run.id,
        project_id=run.project_id,
        workflow_id=run.workflow_id,
        workflow_name=workflow_name,
        trigger=run.trigger,
        status=run.status,
        runtime_summary=run.runtime_summary or {},
        input_payload_json=run.input_payload_json or {},
        output_text=run.output_text or "",
        error_text=run.error_text or "",
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _to_run_list(items: list[Any], total: int, names: dict | None = None) -> RunList:
    names = names or {}
    return RunList(items=[_to_run_read(item, names.get(str(item.workflow_id))) for item in items], total=total)


@router.get("/projects/{project_id}/runs", response_model=RunList)
async def list_runs(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
    db: DBSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_VIEW)
    items, total = await run_svc.list(project_id, skip=skip, limit=limit)
    wf_ids = {str(r.workflow_id) for r in items if r.workflow_id}
    names: dict[str, str] = {}
    if wf_ids:
        result = await db.execute(
            select(Workflow.id, Workflow.name).where(Workflow.id.in_([r.workflow_id for r in items if r.workflow_id]))
        )
        names = {str(row.id): row.name for row in result}
    return _to_run_list(items, total, names)


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def create_run(
    request: Request,
    project_id: UUID,
    data: RunCreate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_EXECUTE)
    run = await run_svc.create(project_id, data)
    # Commit before dispatching so the worker can read the run row immediately.
    await run_svc.db.commit()
    task_id = _dispatch_task("app.worker.tasks.execute_run", str(run.id), str(project_id))
    run.runtime_summary = {**(run.runtime_summary or {}), "dispatch_task_id": task_id}
    await run_svc.db.commit()
    await run_svc.db.refresh(run)
    return _to_run_read(run)


@router.get("/projects/{project_id}/runs/{run_id}", response_model=RunRead)
async def get_run(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_VIEW)
    return _to_run_read(await run_svc.get(run_id, project_id))


@router.patch("/projects/{project_id}/runs/{run_id}", response_model=RunRead)
async def update_run(
    project_id: UUID,
    run_id: UUID,
    data: RunUpdate,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_EXECUTE)
    return _to_run_read(await run_svc.update(run_id, project_id, data))


@router.post("/projects/{project_id}/runs/{run_id}/approve", response_model=RunRead)
async def approve_run(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
) -> Any:
    """Approve a run waiting at an approval step and resume execution."""
    await project_svc.resolve_access(project_id, user, require=Permission.HANDOFF_APPROVE)
    run = await run_svc.get(run_id, project_id)  # ownership + existence
    task_id = _dispatch_task("app.worker.tasks.resume_run", str(run.id), str(project_id))
    run.runtime_summary = {**(run.runtime_summary or {}), "resume_task_id": task_id}
    await run_svc.db.commit()
    await run_svc.db.refresh(run)
    return _to_run_read(run)


@router.post("/projects/{project_id}/runs/{run_id}/reject", response_model=RunRead)
async def reject_run(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
) -> Any:
    """Reject a run waiting at an approval step — cancels and finishes it."""
    await project_svc.resolve_access(project_id, user, require=Permission.HANDOFF_APPROVE)
    return _to_run_read(await RunExecutor(run_svc.db).resume_rejected(run_id, project_id))


@router.post("/projects/{project_id}/runs/{run_id}/retry", response_model=RunRead)
async def retry_run(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
) -> Any:
    """Reset a failed/cancelled/paused run to queued and re-execute from the start."""
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_EXECUTE)
    run = await run_svc.reset_for_retry(run_id, project_id)
    await run_svc.db.commit()
    task_id = _dispatch_task("app.worker.tasks.execute_run", str(run_id), str(project_id))
    run.runtime_summary = {**(run.runtime_summary or {}), "retry_dispatch_task_id": task_id}
    await run_svc.db.commit()
    await run_svc.db.refresh(run)
    return _to_run_read(run)


@router.get("/projects/{project_id}/runs/{run_id}/steps", response_model=RunStepList)
async def list_run_steps(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
) -> Any:
    """Return all recorded steps for a run."""
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_VIEW)
    await run_svc.get(run_id, project_id)
    items, total = await run_repo.list_steps_by_run(run_svc.db, run_id=run_id)
    return RunStepList(items=items, total=total)


@router.post("/projects/{project_id}/runs/{run_id}/override-approve", response_model=RunRead)
async def override_approve_run(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
) -> Any:
    """Override a HAWK vote gate block and resume pipeline execution."""
    await project_svc.resolve_access(project_id, user, require=Permission.HANDOFF_APPROVE)
    run = await run_svc.get(run_id, project_id)
    task_id = _dispatch_task("app.worker.tasks.override_approve_run", str(run.id), str(project_id))
    run.runtime_summary = {**(run.runtime_summary or {}), "override_task_id": task_id}
    await run_svc.db.commit()
    await run_svc.db.refresh(run)
    return _to_run_read(run)


@router.delete(
    "/projects/{project_id}/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_run(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
) -> None:
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_EXECUTE)
    await run_svc.delete(run_id, project_id)


@router.get("/projects/{project_id}/runs/{run_id}/download")
async def download_run_output(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
    format: Literal["markdown", "json", "csv", "text"] = Query("markdown"),
) -> StreamingResponse:
    """Download run output in the specified format."""
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_VIEW)
    run = await run_svc.get(run_id, project_id)
    output = run.output_text or ""
    finished = run.finished_at.isoformat() if isinstance(run.finished_at, datetime) else str(run.finished_at or "")

    if format == "json":
        try:
            parsed = json.loads(output)
        except Exception:
            parsed = {"output": output}
        payload = json.dumps(
            {"run_id": str(run.id), "status": run.status, "finished_at": finished, "data": parsed},
            ensure_ascii=False, indent=2,
        )
        return StreamingResponse(
            iter([payload]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="run-{run_id}.json"'},
        )

    if format == "csv":
        lines = ["run_id,status,finished_at", f"{run.id},{run.status},{finished}"]
        lines.append("")
        for i, line in enumerate(output.splitlines()):
            lines.append(f"{i+1},{line.replace(',', ';')}")
        payload = "\n".join(lines)
        return StreamingResponse(
            iter([payload]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="run-{run_id}.csv"'},
        )

    if format == "text":
        return StreamingResponse(
            iter([output]),
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="run-{run_id}.txt"'},
        )

    # Default: markdown
    md = f"""---
run_id: {run.id}
status: {run.status}
trigger: {run.trigger}
finished_at: {finished}
---

{output}
"""
    return StreamingResponse(
        iter([md]),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="run-{run_id}.md"'},
    )


_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "waiting_approval"}
_STREAM_MAX_SECONDS = 1800  # 30 minutes hard cap


@router.get("/projects/{project_id}/runs/{run_id}/stream")
async def stream_run_logs(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
    db: DBSession,
) -> StreamingResponse:
    """SSE endpoint: streams run_steps as they are created by the Celery worker."""
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_VIEW)
    await run_svc.get(run_id, project_id)  # existence + ownership check

    async def _generate():
        deadline = datetime.now(UTC).timestamp() + _STREAM_MAX_SECONDS
        emitted_ids: set[str] = set()

        while True:
            if datetime.now(UTC).timestamp() > deadline:
                break

            # Re-fetch run status each tick to avoid stale ORM state
            run_row = (await db.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
            if run_row is None:
                break

            current_status = run_row.status
            started_ts = run_row.started_at
            elapsed: int | None = None
            if started_ts is not None:
                ts = started_ts if started_ts.tzinfo else started_ts.replace(tzinfo=UTC)
                elapsed = int((datetime.now(UTC) - ts).total_seconds())

            # Emit any new steps (ordered by creation time)
            step_result = await db.execute(
                select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.created_at)
            )
            all_steps = step_result.scalars().all()

            for idx, step in enumerate(all_steps):
                sid = str(step.id)
                if sid not in emitted_ids:
                    emitted_ids.add(sid)
                    payload = {
                        "step_index": idx,
                        "agent_name": step.step_key,
                        "status": step.status,
                        "output_json": step.output_json or {},
                        "started_at": step.started_at.isoformat() if step.started_at else None,
                        "ended_at": step.finished_at.isoformat() if step.finished_at else None,
                    }
                    yield f"event: step\ndata: {json.dumps(payload)}\n\n"

            # Heartbeat with current run status
            heartbeat = {"status": current_status, "elapsed_seconds": elapsed}
            yield f"event: run_status\ndata: {json.dumps(heartbeat)}\n\n"

            if current_status in _TERMINAL_STATUSES:
                break

            await asyncio.sleep(1.5)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
