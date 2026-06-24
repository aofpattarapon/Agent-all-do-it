"""Phase 6.14.O — targeted DB prompt sync for the manual compile_proposal step.

Surgically updates ONLY the ``compile_proposal`` node's ``config.prompt`` in the manual
"Crypto Trade Pipeline — Proposal to Execution" workflow so the live prompt matches the
seed source (which now restates ``Set approval_status to PENDING_APPROVAL``). The Auto
30m/15m workflows already carry the line and are left untouched.

No topology, gate, schedule, agent, or any other step is modified — only that one prompt
string. Prints a before/after diff and asserts the step set is unchanged.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.commands.seed_crypto_workflow import (
    CRYPTO_TRADE_PIPELINE_WORKFLOW,
    _workflow_prompt_map,
)
from app.db.models.workflow import Workflow
from app.db.session import get_db_context

WORKFLOW_NAME = CRYPTO_TRADE_PIPELINE_WORKFLOW["name"]
STEP_KEY = "compile_proposal"


async def main() -> None:
    expected_prompt = _workflow_prompt_map(WORKFLOW_NAME)[STEP_KEY]
    assert "Set approval_status to PENDING_APPROVAL" in expected_prompt, (
        "seed source missing the PENDING_APPROVAL line — aborting"
    )

    async with get_db_context() as db:
        wf = (
            (await db.execute(select(Workflow).where(Workflow.name == WORKFLOW_NAME)))
            .scalars()
            .first()
        )
        if wf is None:
            print(f"[ABORT] workflow not found: {WORKFLOW_NAME}", flush=True)
            return

        definition = wf.definition_json or {}
        steps = definition.get("steps") or []
        keys_before = [(s.get("key"), s.get("kind")) for s in steps]

        target = next((s for s in steps if s.get("key") == STEP_KEY), None)
        if target is None:
            print(f"[ABORT] {STEP_KEY} step not found in {WORKFLOW_NAME}", flush=True)
            return

        config = target.get("config") or {}
        before = config.get("prompt") or ""
        print(f"[BEFORE] len={len(before)} has_line={'Set approval_status to PENDING_APPROVAL' in before}", flush=True)

        if before == expected_prompt:
            print("[NOOP] prompt already in sync — no write performed", flush=True)
            return

        # Surgical: only this node's config.prompt changes.
        config["prompt"] = expected_prompt
        target["config"] = config
        wf.definition_json = definition
        flag_modified(wf, "definition_json")
        await db.commit()

        # Re-read and verify.
        await db.refresh(wf)
        steps_after = (wf.definition_json or {}).get("steps") or []
        keys_after = [(s.get("key"), s.get("kind")) for s in steps_after]
        after = next(
            (s.get("config", {}).get("prompt") for s in steps_after if s.get("key") == STEP_KEY),
            "",
        )

        assert keys_before == keys_after, "STEP TOPOLOGY CHANGED — unexpected!"
        assert after == expected_prompt, "prompt not persisted as expected"
        # Every non-target step prompt must be byte-identical.
        changed = []
        for sb, sa in zip(steps, steps_after, strict=True):
            if sb.get("key") == STEP_KEY:
                continue
            if (sb.get("config") or {}).get("prompt") != (sa.get("config") or {}).get("prompt"):
                changed.append(sb.get("key"))
        assert not changed, f"OTHER STEP PROMPTS CHANGED: {changed}"

        print(f"[AFTER] len={len(after)} has_line={'Set approval_status to PENDING_APPROVAL' in after}", flush=True)
        print(f"[OK] synced {STEP_KEY} for '{WORKFLOW_NAME}'; {len(keys_after)} steps unchanged", flush=True)


asyncio.run(main())
