"""Inbound webhook endpoints — trigger workflow runs from external systems."""

import hashlib
import hmac
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DBSession, RunSvc, WorkflowSvc
from app.core.exceptions import AuthorizationError
from app.db.models.trigger import Trigger
from app.db.models.workflow import Run
from app.db.session import get_db_context
from app.schemas.run import RunCreate
from app.services.run_executor import RunExecutor

logger = logging.getLogger(__name__)
router = APIRouter()


async def _execute_bg(run_id: UUID, project_id: UUID) -> None:
    """Background entrypoint — runs the executor on a fresh DB session."""
    try:
        async with get_db_context() as db:
            await RunExecutor(db).execute(run_id, project_id)
    except Exception as exc:
        logger.exception("Background webhook run execution failed for run %s: %s", run_id, exc)


@router.post(
    "/projects/{project_id}/workflows/{workflow_id}/webhook",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_workflow_webhook(
    project_id: UUID,
    workflow_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    workflow_svc: WorkflowSvc,
    run_svc: RunSvc,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> dict[str, Any]:
    """Trigger a workflow run from an external system via webhook.

    The request body is passed as input_payload to the run.
    Optionally validates X-Webhook-Secret header against workflow's
    ``definition_json.webhook_secret`` config field.
    """
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}

    # Load workflow — raises NotFoundError (→ 404) if absent or wrong project
    workflow = await workflow_svc.get(workflow_id, project_id)

    # Optional secret validation
    definition = workflow.definition_json or {}
    expected_secret: str | None = definition.get("webhook_secret")  # type: ignore[assignment]
    if expected_secret and x_webhook_secret != expected_secret:
        raise AuthorizationError(message="Invalid webhook secret")

    # Create the run record
    run = await run_svc.create(
        project_id,
        RunCreate(
            workflow_id=workflow_id,
            trigger="webhook",
            input_payload_json=body,
        ),
    )
    logger.info("Webhook triggered run %s for workflow %s", run.id, workflow_id)

    # Execute asynchronously on a fresh session
    background_tasks.add_task(_execute_bg, run.id, project_id)

    return {
        "run_id": str(run.id),
        "status": run.status,
        "message": "Workflow run queued",
    }


# ── Trigger registry webhooks (HMAC-verified) ────────────────────────────────

@router.post("/webhooks/{webhook_path}", status_code=status.HTTP_202_ACCEPTED)
async def receive_trigger_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, Any]:
    """Accept an HMAC-signed webhook delivery and queue the associated workflow run.

    Delivery must include header:
      X-Hub-Signature-256: sha256=<hex_digest>

    The digest is HMAC-SHA256 of the raw request body, signed with the
    Trigger's ``webhook_secret``.
    """
    body = await request.body()

    result = await db.execute(
        select(Trigger).where(
            Trigger.webhook_path == webhook_path,
            Trigger.kind == "webhook",
            Trigger.is_enabled.is_(True),
        )
    )
    trigger = result.scalar_one_or_none()
    if trigger is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not registered")

    if trigger.webhook_secret:
        _verify_hmac(body, trigger.webhook_secret, x_hub_signature_256)

    background_tasks.add_task(_fire_trigger_run, trigger.project_id, trigger.workflow_id, trigger.name, body)
    return {"accepted": True, "trigger_id": str(trigger.id)}


async def _fire_trigger_run(
    project_id: UUID, workflow_id: UUID, trigger_name: str, body: bytes
) -> None:
    try:
        payload = json.loads(body) if body else {}
    except (json.JSONDecodeError, ValueError):
        payload = {"raw": body.decode("utf-8", errors="replace")}

    async with get_db_context() as db:
        run = Run(
            project_id=project_id,
            workflow_id=workflow_id,
            status="queued",
            task=f"Webhook: {trigger_name}",
            input_payload=payload,
        )
        db.add(run)
        await db.flush()
        await db.refresh(run)
        await RunExecutor(db).execute(run.id, project_id)


def _verify_hmac(body: bytes, secret: str, header: str | None) -> None:
    if not header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )
    try:
        scheme, sig_hex = header.split("=", 1)
        if scheme != "sha256":
            raise ValueError("bad scheme")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature format — expected 'sha256=<hex>'",
        ) from exc
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig_hex):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature mismatch",
        )
