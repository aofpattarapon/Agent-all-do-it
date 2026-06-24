"""Phase 6.14.N-service — Trigger exactly ONE fresh Proposal-to-Execution run.

In-container service-layer trigger (approved exception: no user JWT available, so the
HTTP API path cannot be used). Mirrors the HTTP create_run endpoint EXACTLY:
  RunService.create(project_id, RunCreate(...)) -> db.commit() ->
  celery_app.send_task("app.worker.tasks.execute_run", [run_id, project_id]).

Does NOT use /retry. Does NOT create any trade row. Does NOT enable schedules.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.db.session import get_db_context
from app.schemas.run import RunCreate
from app.services.run import RunService
from app.worker.celery_app import celery_app

PROJECT_ID = UUID("288bc95a-b4da-46e7-bdfa-b5630233f586")
WORKFLOW_ID = UUID("554e8f6b-ec52-412f-8fbf-6223291d5445")


async def main() -> None:
    data = RunCreate(
        workflow_id=WORKFLOW_ID,
        trigger="manual_6_14n_service",
        input_payload_json={
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "project_mode": "demo",
            "workflow_name": "Crypto Trade Pipeline — Proposal to Execution",
        },
    )
    async with get_db_context() as db:
        svc = RunService(db)
        run = await svc.create(PROJECT_ID, data)
        await db.commit()
        run_id = run.id
        wf_id = run.workflow_id
        payload = run.input_payload_json

    # Same dispatch contract as the HTTP create_run endpoint.
    res = celery_app.send_task("app.worker.tasks.execute_run", args=[str(run_id), str(PROJECT_ID)])

    print(f"[TRIGGERED] run_id={run_id}", flush=True)
    print(f"[TRIGGERED] workflow_id={wf_id}", flush=True)
    print(f"[TRIGGERED] trigger=manual_6_14n_service", flush=True)
    print(f"[TRIGGERED] input_payload_json={payload}", flush=True)
    print(f"[TRIGGERED] dispatch_task_id={res.id}", flush=True)
    assert wf_id is not None, "workflow_id must be non-null"
    assert payload.get("symbol") == "BTCUSDT", "symbol BTCUSDT must be present"
    print("[OK] workflow_id non-null and symbol=BTCUSDT confirmed", flush=True)


asyncio.run(main())
