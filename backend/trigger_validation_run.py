"""Phase 6.8 Runtime Validation — single scheduler-shaped run trigger.

Replicates exactly what schedule_runner._tick() does for the Auto 30m workflow:
1. Check no active run exists for this workflow (overlap guard)
2. Create a run row via run_svc.create()
3. Commit
4. Dispatch Celery task execute_run

Do NOT run this script more than once without approval.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from uuid import UUID

from sqlalchemy import select

from app.db.models.workflow import Run, Workflow
from app.db.session import async_session_maker
from app.schemas.run import RunCreate
from app.services.run import RunService

TARGET_WORKFLOW_ID = UUID("c662bc4b-17f2-482f-b445-69927c3b9718")  # Crypto Trade Pipeline — Auto 30m
TARGET_PROJECT_ID = UUID("288bc95a-b4da-46e7-bdfa-b5630233f586")   # Binance Testnet — BTCUSDT Pipeline

INPUT_PAYLOAD = {
    "symbol": "BTCUSDT",
    "timeframe": "4h",
    "project_mode": "paper",
    "workflow_name": "Crypto Trade Pipeline — Auto 30m",
}


def _dispatch(run_id: str, project_id: str) -> str:
    code = (
        "import sys\n"
        "from app.worker.celery_app import celery_app\n"
        "res = celery_app.send_task(sys.argv[1], args=sys.argv[2:])\n"
        "print(res.id)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, "app.worker.tasks.execute_run", run_id, project_id],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    task_id = proc.stdout.strip().splitlines()[-1].strip()
    if not task_id:
        raise RuntimeError("No Celery task ID returned")
    return task_id


async def main() -> int:
    async with async_session_maker() as db:
        # Confirm workflow exists
        wf = (await db.execute(select(Workflow).where(Workflow.id == TARGET_WORKFLOW_ID))).scalar_one_or_none()
        if wf is None:
            print(f"ABORT: workflow {TARGET_WORKFLOW_ID} not found")
            return 1
        print(f"Workflow: {wf.name}  [{wf.id}]")
        print(f"Project:  {TARGET_PROJECT_ID}")

        # Overlap guard — same as schedule_runner
        active = (await db.execute(
            select(Run).where(
                Run.workflow_id == TARGET_WORKFLOW_ID,
                Run.status.in_(["queued", "running", "waiting_approval"]),
            ).limit(1)
        )).scalar_one_or_none()
        if active is not None:
            print(f"ABORT: active run already exists — id={active.id} status={active.status}")
            print("The overlap guard prevents a duplicate dispatch.")
            return 1

        # Create the run
        run_svc = RunService(db)
        run = await run_svc.create(
            project_id=TARGET_PROJECT_ID,
            data=RunCreate(
                workflow_id=TARGET_WORKFLOW_ID,
                trigger="schedule",
                input_payload_json=INPUT_PAYLOAD,
            ),
        )
        await db.commit()
        print(f"\nRun created:  id={run.id}  status={run.status}  trigger={run.trigger}")

        # Dispatch Celery task
        task_id = _dispatch(str(run.id), str(TARGET_PROJECT_ID))
        print(f"Celery task dispatched:  task_id={task_id}")
        print(f"\nrun_id={run.id}")
        print(f"project_id={TARGET_PROJECT_ID}")
        print(f"workflow={wf.name}")
        print(f"payload={INPUT_PAYLOAD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
