"""Phase 6.14.R — targeted DB prompt sync for the hardened compile_proposal SL geometry rules.

Surgically updates ONLY the ``compile_proposal`` node's ``config.prompt`` in each workflow that
carries a compile_proposal step — the manual "Crypto Trade Pipeline — Proposal to Execution" and
the two auto pipelines (Auto 30m / Auto 15m) — so the live prompt matches the hardened seed source
(``_COMPILE_PROPOSAL_DIRECTIONAL_RULES`` now forbids stop_loss == entry/reference and requires the
strict max()/min() direction anchor).

No topology, gate, schedule, agent, or any other step is modified — only that one prompt string per
workflow. Prints a before/after diff per workflow and asserts:
  * step key+kind topology is unchanged,
  * every NON-target step prompt is byte-identical,
  * every NON-target step config (gate configs included) is byte-identical,
  * the new geometry markers are present after the write.

The schedules table is never touched by this script.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.commands.seed_crypto_workflow import (
    CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW,
    CRYPTO_TRADE_PIPELINE_WORKFLOW,
    _workflow_prompt_map,
)
from app.db.models.workflow import Workflow
from app.db.session import get_db_context

STEP_KEY = "compile_proposal"
MARKERS = (
    "NEVER equal entry",
    "max(entry, reference_price, primary_entry)",
    "min(entry, reference_price, primary_entry)",
)
WORKFLOW_NAMES = (
    CRYPTO_TRADE_PIPELINE_WORKFLOW["name"],
    CRYPTO_TRADE_PIPELINE_AUTO_WORKFLOW["name"],
    CRYPTO_TRADE_PIPELINE_AUTO_15M_WORKFLOW["name"],
)


def _markers(text: str) -> str:
    return ",".join(f"{m.split('(')[0].strip()}={int(m in text)}" for m in MARKERS)


async def _sync_one(db, name: str) -> None:
    expected = _workflow_prompt_map(name)[STEP_KEY]
    assert all(m in expected for m in MARKERS), f"seed source for {name!r} missing new markers — aborting"

    wf = (await db.execute(select(Workflow).where(Workflow.name == name))).scalars().first()
    if wf is None:
        print(f"[SKIP] workflow not found: {name}", flush=True)
        return

    definition = wf.definition_json or {}
    steps = definition.get("steps") or []
    topo_before = [(s.get("key"), s.get("kind")) for s in steps]
    target = next((s for s in steps if s.get("key") == STEP_KEY), None)
    if target is None:
        print(f"[SKIP] {STEP_KEY} step not found in {name}", flush=True)
        return

    config = target.get("config") or {}
    before = config.get("prompt") or ""
    print(f"[BEFORE] {name!r} len={len(before)} {_markers(before)}", flush=True)

    if before == expected:
        print(f"[NOOP] {name!r} already in sync — no write performed", flush=True)
        return

    config["prompt"] = expected
    target["config"] = config
    wf.definition_json = definition
    flag_modified(wf, "definition_json")
    await db.commit()
    await db.refresh(wf)

    steps_after = (wf.definition_json or {}).get("steps") or []
    topo_after = [(s.get("key"), s.get("kind")) for s in steps_after]
    after = next((s.get("config", {}).get("prompt") for s in steps_after if s.get("key") == STEP_KEY), "")

    assert topo_before == topo_after, f"STEP TOPOLOGY CHANGED for {name!r}"
    assert after == expected, f"prompt not persisted as expected for {name!r}"
    # Every non-target step: prompt AND full config must be byte-identical (gate configs included).
    changed_prompt, changed_config = [], []
    for sb, sa in zip(steps, steps_after, strict=True):
        if sb.get("key") == STEP_KEY:
            continue
        if (sb.get("config") or {}).get("prompt") != (sa.get("config") or {}).get("prompt"):
            changed_prompt.append(sb.get("key"))
        if (sb.get("config") or {}) != (sa.get("config") or {}):
            changed_config.append(sb.get("key"))
    assert not changed_prompt, f"OTHER STEP PROMPTS CHANGED in {name!r}: {changed_prompt}"
    assert not changed_config, f"OTHER STEP CONFIGS CHANGED in {name!r}: {changed_config}"
    assert all(m in after for m in MARKERS), f"markers missing after write for {name!r}"

    print(f"[AFTER]  {name!r} len={len(after)} {_markers(after)}", flush=True)
    print(f"[OK] synced {STEP_KEY} for {name!r}; {len(topo_after)} steps unchanged", flush=True)


async def main() -> None:
    async with get_db_context() as db:
        for name in WORKFLOW_NAMES:
            await _sync_one(db, name)


asyncio.run(main())
