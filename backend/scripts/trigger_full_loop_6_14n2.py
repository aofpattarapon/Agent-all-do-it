"""Phase 6.14.N2-service — trigger exactly ONE fresh Proposal-to-Execution run.

Mirrors the application's create_run route (app/api/routes/v1/runs.py) precisely:
  1. RunService.create(project_id, RunCreate(...))   # service/repository path
  2. db.commit()                                      # commit before dispatch
  3. celery_app.send_task("app.worker.tasks.execute_run", args=[run_id, project_id])

The ONLY step deliberately skipped is project_svc.resolve_access(...) — the JWT/RBAC
gate — because no user JWT is available in this service-layer trigger. No DB rows are
manually created or mutated; the run is created through the same service/repository the
HTTP route uses. No /retry is used.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.db.session import get_db_context
from app.services.run import RunCreate, RunService
from app.worker.celery_app import celery_app

WORKFLOW_ID = UUID("554e8f6b-ec52-412f-8fbf-6223291d5445")
PROJECT_ID = UUID("288bc95a-b4da-46e7-bdfa-b5630233f586")
PAYLOAD = {
    "symbol": "BTCUSDT",
    "timeframe": "4h",
    "project_mode": "demo",
    "workflow_name": "Crypto Trade Pipeline — Proposal to Execution",
}


async def main() -> None:
    async with get_db_context() as db:
        svc = RunService(db)
        data = RunCreate(workflow_id=WORKFLOW_ID, trigger="manual", input_payload_json=PAYLOAD)
        run = await svc.create(PROJECT_ID, data)
        await db.commit()
        await db.refresh(run)

        rid = str(run.id)
        print(f"[CREATED] run_id={rid}", flush=True)
        print(f"[CREATED] workflow_id={run.workflow_id}", flush=True)
        print(f"[CREATED] trigger={run.trigger} status={run.status}", flush=True)
        print(f"[CREATED] payload_symbol={(run.input_payload_json or {}).get('symbol')}", flush=True)

        assert run.workflow_id is not None, "created run has NULL workflow_id"
        assert (run.input_payload_json or {}).get("symbol") == "BTCUSDT", "payload missing symbol=BTCUSDT"

        # Mirror the route's dispatch (a standalone process is the known-good producer path).
        res = celery_app.send_task("app.worker.tasks.execute_run", args=[rid, str(PROJECT_ID)])
        print(f"[DISPATCHED] task_id={res.id} task=app.worker.tasks.execute_run", flush=True)
        print(f"[OK] one fresh run triggered: {rid}", flush=True)


asyncio.run(main())
