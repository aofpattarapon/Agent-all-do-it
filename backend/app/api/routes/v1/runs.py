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
from app.core.rate_limit import limiter
from app.core.rbac import Permission
from app.db.models.crypto_trading import MarketSnapshot, Position, TradeExecution, TradeProposal
from app.db.models.workflow import Run, RunStep, Workflow
from app.repositories import run as run_repo
from app.schemas.metrics import RunSummary
from app.schemas.run import (
    NormalizedStatusRead,
    RunCreate,
    RunList,
    RunRead,
    RunStepList,
    RunUpdate,
    TradeOutcomeRead,
)
from app.services.run_executor import RunExecutor
from app.services.run_metrics import build_run_summary
from app.services.run_status_classifier import to_display_status
from app.services.run_status_normalizer import normalize_run_status
from app.services.run_trade_outcome import TradeEvidence, build_run_trade_outcome
from app.services.workflow_category_classifier import classify_workflow_category

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


def _to_run_read(
    run: Any,
    workflow_name: str | None = None,
    trade_outcome: dict | None = None,
    normalized_status: dict | None = None,
) -> RunRead:
    """Convert an ORM run instance to a concrete response DTO inside the request context."""
    outcome_field: TradeOutcomeRead | None = None
    if trade_outcome is not None:
        outcome_field = TradeOutcomeRead(**trade_outcome)
    normalized_field: NormalizedStatusRead | None = None
    if normalized_status is not None:
        normalized_field = NormalizedStatusRead(**normalized_status)
    display = to_display_status(trade_outcome, run.status or "", run.pause_reason or "")
    return RunRead(
        id=run.id,
        project_id=run.project_id,
        workflow_id=run.workflow_id,
        workflow_name=workflow_name,
        trigger=run.trigger,
        status=run.status,
        pause_reason=run.pause_reason or None,
        runtime_summary=run.runtime_summary or {},
        input_payload_json=run.input_payload_json or {},
        output_text=run.output_text or "",
        error_text=run.error_text or "",
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
        trade_outcome=outcome_field,
        normalized_status=normalized_field,
        **display,
    )


async def _fetch_trade_outcomes(db: Any, run_ids: list[UUID]) -> dict[UUID, dict]:
    """
    Batch-fetch trade evidence for a list of run_ids and compute derived outcomes.
    Returns a dict of {run_id: trade_outcome_dict}.
    Performs a constant number of DB queries regardless of list size.
    """
    if not run_ids:
        return {}

    # 1. Proposals for these runs
    prop_result = await db.execute(select(TradeProposal).where(TradeProposal.run_id.in_(run_ids)))
    proposals: list[TradeProposal] = list(prop_result.scalars().all())
    proposals_by_run: dict[UUID, TradeProposal] = {p.run_id: p for p in proposals}

    # 2. Executions for the found proposals
    proposal_ids = [p.id for p in proposals]
    executions_by_proposal: dict[UUID, TradeExecution] = {}
    if proposal_ids:
        exec_result = await db.execute(
            select(TradeExecution).where(TradeExecution.proposal_id.in_(proposal_ids))
        )
        for ex in exec_result.scalars().all():
            executions_by_proposal[ex.proposal_id] = ex

    # 3. Positions for the found executions
    execution_ids = [e.id for e in executions_by_proposal.values()]
    positions_by_execution: dict[UUID, Position] = {}
    if execution_ids:
        pos_result = await db.execute(
            select(Position).where(Position.execution_id.in_(execution_ids))
        )
        for pos in pos_result.scalars().all():
            positions_by_execution[pos.execution_id] = pos

    # 4. Winrate gate steps for these runs (to distinguish limit vs reject)
    wg_result = await db.execute(
        select(RunStep).where(
            RunStep.run_id.in_(run_ids),
            RunStep.step_kind == "winrate_trade_gate",
            RunStep.status == "completed",
        )
    )
    wg_by_run: dict[UUID, dict] = {}
    wg_output_by_run: dict[UUID, str] = {}
    for step in wg_result.scalars().all():
        out = step.output_json or {}
        wg_by_run[step.run_id] = out.get("meta") or {}
        wg_output_by_run[step.run_id] = out.get("output") or ""

    # 5. Market snapshots for research runs
    ms_result = await db.execute(
        select(MarketSnapshot).where(MarketSnapshot.run_id.in_(run_ids))
    )
    market_snapshots_by_run: dict[UUID, list[dict]] = {}
    for ms in ms_result.scalars().all():
        market_snapshots_by_run.setdefault(ms.run_id, []).append(
            {
                "market_regime": ms.market_regime,
                "trade_permission": ms.trade_permission,
            }
        )

    # 6. Position monitor step outputs for monitor runs
    pm_result = await db.execute(
        select(RunStep).where(
            RunStep.run_id.in_(run_ids),
            RunStep.step_kind == "position_monitor",
            RunStep.status == "completed",
        )
    )
    monitor_snapshot_by_run: dict[UUID, list[dict]] = {}
    for step in pm_result.scalars().all():
        out = step.output_json or {}
        try:
            snapshot = json.loads(out.get("output") or "[]")
            if not isinstance(snapshot, list):
                snapshot = []
        except Exception:
            snapshot = []
        monitor_snapshot_by_run[step.run_id] = snapshot

    # 7. Screener step outputs for screener runs
    screener_result = await db.execute(
        select(RunStep).where(
            RunStep.run_id.in_(run_ids),
            RunStep.step_kind == "coin_screener",
            RunStep.status == "completed",
        )
    )
    screener_meta_by_run: dict[UUID, dict] = {}
    for step in screener_result.scalars().all():
        out = step.output_json or {}
        screener_meta_by_run[step.run_id] = out.get("meta") or {}

    # 8. Position statuses touched by these runs (for monitor attention/closed detection)
    positions_by_run_result = await db.execute(
        select(Position).where(Position.execution_id.in_(execution_ids))
    )
    position_statuses_by_run: dict[UUID, set[str]] = {}
    for pos in positions_by_run_result.scalars().all():
        # Map position back to run via execution -> proposal -> run
        for ex_id, ex in executions_by_proposal.items():
            if ex.id == pos.execution_id:
                # Find proposal for this execution
                for proposal in proposals:
                    if proposal.id == ex.proposal_id:
                        position_statuses_by_run.setdefault(proposal.run_id, set()).add(pos.status)
                        break
                break

    # Build outcome per run
    outcomes: dict[UUID, dict] = {}
    for rid in run_ids:
        proposal = proposals_by_run.get(rid)
        execution: TradeExecution | None = None
        position: Position | None = None
        if proposal is not None:
            execution = executions_by_proposal.get(proposal.id)
            if execution is not None:
                position = positions_by_execution.get(execution.id)

        outcomes[rid] = {
            "proposal": proposal,
            "execution": execution,
            "position": position,
            "wg_meta": wg_by_run.get(rid),
            "wg_output": wg_output_by_run.get(rid, ""),
            "market_snapshot": market_snapshots_by_run.get(rid),
            "monitor_snapshot": monitor_snapshot_by_run.get(rid),
            "screener_meta": screener_meta_by_run.get(rid),
            "position_statuses": position_statuses_by_run.get(rid, set()),
        }

    return outcomes


def _compute_outcome(run: Any, evidence_row: dict | None) -> dict:
    """Build TradeEvidence from a run ORM object + evidence_row dict, then compute outcome."""
    if evidence_row is None:
        evidence_row = {}
    proposal: TradeProposal | None = evidence_row.get("proposal")
    execution: TradeExecution | None = evidence_row.get("execution")
    position: Position | None = evidence_row.get("position")

    ev = TradeEvidence(
        run_status=run.status or "",
        pause_reason=run.pause_reason or "",
        error_text=run.error_text or "",
        proposal_status=proposal.status if proposal is not None else None,
        proposal_sage_approved=proposal.sage_approved if proposal is not None else None,
        execution_status=execution.execution_status if execution is not None else None,
        position_status=position.status if position is not None else None,
        winrate_gate_meta=evidence_row.get("wg_meta"),
        winrate_gate_output=evidence_row.get("wg_output"),
    )
    return build_run_trade_outcome(ev)


def _compute_normalized_status(
    run: Any,
    workflow_name: str | None,
    evidence_row: dict | None,
) -> dict:
    """Build normalized status from a run ORM object + evidence_row dict."""
    if evidence_row is None:
        evidence_row = {}
    proposal: TradeProposal | None = evidence_row.get("proposal")
    execution: TradeExecution | None = evidence_row.get("execution")
    position: Position | None = evidence_row.get("position")

    ns = normalize_run_status(
        run,
        workflow_name=workflow_name,
        proposal=proposal,
        execution=execution,
        position=position,
        winrate_gate_meta=evidence_row.get("wg_meta"),
        market_snapshot=evidence_row.get("market_snapshot"),
        monitor_snapshot=evidence_row.get("monitor_snapshot"),
        position_statuses=evidence_row.get("position_statuses"),
        screener_meta=evidence_row.get("screener_meta"),
    )
    return ns.to_dict()


def _to_run_list(
    items: list[Any],
    total: int,
    names: dict | None = None,
    outcomes: dict | None = None,
) -> RunList:
    names = names or {}
    outcomes = outcomes or {}
    return RunList(
        items=[
            _to_run_read(
                item,
                names.get(str(item.workflow_id)),
                _compute_outcome(item, outcomes.get(item.id)),
                _compute_normalized_status(item, names.get(str(item.workflow_id)), outcomes.get(item.id)),
            )
            for item in items
        ],
        total=total,
    )


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
            select(Workflow.id, Workflow.name).where(
                Workflow.id.in_([r.workflow_id for r in items if r.workflow_id])
            )
        )
        names = {str(row.id): row.name for row in result}
    run_ids = [r.id for r in items]
    outcomes = await _fetch_trade_outcomes(db, run_ids)
    return _to_run_list(items, total, names, outcomes)


async def classify_project_runs(db: Any, project_id: UUID) -> list[dict[str, Any]]:
    """Classify every run in a project by canonical ``display_status`` + workflow category.

    Read-only. Returns one mapping per run carrying the display fields produced by
    :func:`to_display_status` plus ``workflow_category``. Reused by the run-summary and
    performance-summary endpoints so both share a single source of truth.
    """
    result = await db.execute(select(Run).where(Run.project_id == project_id))
    runs = list(result.scalars().all())
    if not runs:
        return []

    wf_ids = [r.workflow_id for r in runs if r.workflow_id]
    workflows_by_id: dict[Any, Any] = {}
    if wf_ids:
        wf_result = await db.execute(select(Workflow).where(Workflow.id.in_(wf_ids)))
        workflows_by_id = {wf.id: wf for wf in wf_result.scalars().all()}

    outcomes = await _fetch_trade_outcomes(db, [r.id for r in runs])

    classified: list[dict[str, Any]] = []
    for run in runs:
        evidence_row = outcomes.get(run.id)
        outcome = _compute_outcome(run, evidence_row)
        display = to_display_status(outcome, run.status or "", run.pause_reason or "")
        workflow = workflows_by_id.get(run.workflow_id)
        category = classify_workflow_category(
            workflow, getattr(workflow, "name", None) if workflow is not None else None
        )
        classified.append({**display, "workflow_category": category})
    return classified


@router.get("/projects/{project_id}/runs/summary", response_model=RunSummary)
async def get_runs_summary(
    project_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    db: DBSession,
) -> Any:
    """Backend-authoritative run counts by canonical display status (read-only).

    Active runs are excluded from ``terminal``; ``complete-reject`` and ``limit`` are
    never counted as errors. ``trade_pipeline`` reports the trade-category subset.
    """
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_VIEW)
    classified = await classify_project_runs(db, project_id)
    return build_run_summary(classified)


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
    return _to_run_read(
        run,
        normalized_status=_compute_normalized_status(run, None, None),
    )


@router.get("/projects/{project_id}/runs/{run_id}", response_model=RunRead)
async def get_run(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
    db: DBSession,
) -> Any:
    await project_svc.resolve_access(project_id, user, require=Permission.RUN_VIEW)
    run = await run_svc.get(run_id, project_id)
    outcomes = await _fetch_trade_outcomes(db, [run.id])
    workflow_name: str | None = None
    if run.workflow_id is not None:
        wf_row = await db.execute(select(Workflow.name).where(Workflow.id == run.workflow_id))
        workflow_name = wf_row.scalar_one_or_none()
    evidence = outcomes.get(run.id)
    return _to_run_read(
        run,
        workflow_name=workflow_name,
        trade_outcome=_compute_outcome(run, evidence),
        normalized_status=_compute_normalized_status(run, workflow_name, evidence),
    )


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
    run = await run_svc.update(run_id, project_id, data)
    return _to_run_read(
        run,
        normalized_status=_compute_normalized_status(run, None, None),
    )


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
    return _to_run_read(
        run,
        normalized_status=_compute_normalized_status(run, None, None),
    )


@router.post("/projects/{project_id}/runs/{run_id}/reject", response_model=RunRead)
async def reject_run(
    project_id: UUID,
    run_id: UUID,
    user: CurrentUser,
    project_svc: ProjectSvc,
    run_svc: RunSvc,
    db: DBSession,
) -> Any:
    """Reject a run waiting at an approval step — cancels and finishes it."""
    await project_svc.resolve_access(project_id, user, require=Permission.HANDOFF_APPROVE)
    run = await RunExecutor(run_svc.db).resume_rejected(run_id, project_id)
    workflow_name: str | None = None
    if run.workflow_id is not None:
        wf_row = await db.execute(select(Workflow.name).where(Workflow.id == run.workflow_id))
        workflow_name = wf_row.scalar_one_or_none()
    return _to_run_read(
        run,
        workflow_name=workflow_name,
        normalized_status=_compute_normalized_status(run, workflow_name, None),
    )


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
    return _to_run_read(
        run,
        normalized_status=_compute_normalized_status(run, None, None),
    )


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
    return _to_run_read(
        run,
        normalized_status=_compute_normalized_status(run, None, None),
    )


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
    finished = (
        run.finished_at.isoformat()
        if isinstance(run.finished_at, datetime)
        else str(run.finished_at or "")
    )

    if format == "json":
        try:
            parsed = json.loads(output)
        except Exception:
            parsed = {"output": output}
        payload = json.dumps(
            {"run_id": str(run.id), "status": run.status, "finished_at": finished, "data": parsed},
            ensure_ascii=False,
            indent=2,
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
            lines.append(f"{i + 1},{line.replace(',', ';')}")
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
