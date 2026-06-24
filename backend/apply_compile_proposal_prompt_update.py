"""Targeted compile_proposal prompt-only DB update.

Replaces ONLY the ``config.prompt`` field of the ``compile_proposal`` step in the three
crypto trade pipeline workflows, swapping the stale prompt for the current code template
(which injects ``$hawk_vote_result`` + ``$hawk_invalidation_levels`` and carries the
LONG/SHORT directional SL/TP invariant + BLOCKED-instead-of-fabricate instruction).

Everything else in ``definition_json`` is left byte-for-byte identical: nodes, edges,
version, agent_key UUIDs, trigger/schedule, HAWK/SAGE/other step prompts, and every other
step config key.

Usage:
    uv run python apply_compile_proposal_prompt_update.py            # dry-run (no commit)
    uv run python apply_compile_proposal_prompt_update.py --apply    # commit the 3 updates
"""

from __future__ import annotations

import asyncio
import copy
import sys

from sqlalchemy import select

from app.commands.seed_crypto_workflow import _workflow_prompt_map
from app.db.models.workflow import Workflow
from app.db.session import async_session_maker

_TARGET_WORKFLOWS = {
    "Crypto Trade Pipeline — Proposal to Execution",
    "Crypto Trade Pipeline — Auto 15m",
    "Crypto Trade Pipeline — Auto 30m",
}
_STEP_KEY = "compile_proposal"
_TOK_VOTE = "$hawk_vote_result"
_TOK_INVAL = "$hawk_invalidation_levels"
_RULE_MARK = "DIRECTIONAL SL/TP INVARIANT"
_EXPECTED_CHANGES = 3


def _topology_fingerprint(definition: dict) -> dict:
    """Everything that must NOT change: name, version, nodes, edges, trigger, and for every
    step its key + kind + agent_key + all config keys EXCEPT the compile_proposal prompt we
    intend to edit. Non-target prompts ARE included, so any change to them is caught."""
    steps_fp = []
    for step in definition.get("steps", []):
        key = step.get("key", "")
        config = dict(step.get("config") or {})
        if key == _STEP_KEY:
            config.pop("prompt", None)  # the only field we are allowed to touch
        steps_fp.append(
            {
                "key": key,
                "kind": step.get("kind"),
                "agent_key": step.get("agent_key"),
                "config": config,
            }
        )
    return {
        "name": definition.get("name"),
        "version": definition.get("version"),
        "nodes": definition.get("nodes"),
        "edges": definition.get("edges"),
        "trigger_config": definition.get("trigger_config"),
        "trigger_kind": definition.get("trigger_kind"),
        "steps": steps_fp,
    }


def _flags(prompt: str) -> tuple[bool, bool, bool]:
    return (_TOK_VOTE in prompt, _TOK_INVAL in prompt, _RULE_MARK in prompt)


async def main(apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== compile_proposal prompt-only update [{mode}] ===\n")

    total_changes = 0
    already_current = 0
    topology_violations = 0
    nontarget_violations = 0
    updated_ids: list[str] = []

    async with async_session_maker() as db:
        workflows = (
            (await db.execute(select(Workflow).where(Workflow.name.in_(_TARGET_WORKFLOWS))))
            .scalars()
            .all()
        )
        found = {wf.name for wf in workflows}
        missing = _TARGET_WORKFLOWS - found
        if missing:
            print(f"WARNING: target workflow(s) not found: {sorted(missing)}\n")

        for wf in workflows:
            old_def = wf.definition_json or {}
            name = old_def.get("name") or wf.name
            prompt_map = _workflow_prompt_map(name)
            new_prompt = (prompt_map or {}).get(_STEP_KEY, "")
            if not new_prompt:
                print(f"SKIP {name}: no compile_proposal template in prompt map\n")
                continue

            new_def = copy.deepcopy(old_def)
            before_fp = _topology_fingerprint(old_def)

            step = next(
                (s for s in new_def.get("steps", []) if s.get("key") == _STEP_KEY), None
            )
            if step is None:
                print(f"SKIP {name}: no compile_proposal step found\n")
                continue

            config = step.get("config") or {}
            old_prompt = config.get("prompt") or ""
            ov, oi, orr = _flags(old_prompt)
            nv, ni, nrr = _flags(new_prompt)

            print(f"Workflow: {name}  [{wf.id}]")
            print(f"  old_len={len(old_prompt)} new_len={len(new_prompt)}")
            print(
                f"  old_has_hawk_vote_result={ov} old_has_hawk_invalidation_levels={oi} "
                f"old_has_directional_rules={orr}"
            )
            print(
                f"  new_has_hawk_vote_result={nv} new_has_hawk_invalidation_levels={ni} "
                f"new_has_directional_rules={nrr}"
            )

            if old_prompt != new_prompt:
                config["prompt"] = new_prompt
                step["config"] = config
                total_changes += 1
                print("  -> change staged")
            else:
                already_current += 1
                print("  -> already current (no change)")

            # Integrity check: nothing but the compile_proposal prompt may differ.
            after_fp = _topology_fingerprint(new_def)
            if before_fp != after_fp:
                topology_violations += 1
                print("  !! TOPOLOGY/NON-TARGET VIOLATION DETECTED — aborting this workflow")
                for b, a in zip(before_fp["steps"], after_fp["steps"], strict=False):
                    if b != a:
                        print(f"     changed step fingerprint: {b.get('key')}")
                        nontarget_violations += 1
                print()
                continue

            if apply:
                wf.definition_json = new_def  # reassign whole object → marks JSONB dirty
                updated_ids.append(str(wf.id))
            print()

        print("---")
        print(f"compile_proposal prompt changes staged: {total_changes}")
        print(f"already current (no change): {already_current}")
        print(f"topology violations: {topology_violations}")
        print(f"non-target prompt violations: {nontarget_violations}")

        if topology_violations or nontarget_violations:
            print("\nABORT: integrity violation — rolling back, nothing committed.")
            await db.rollback()
            return 2

        # Allow a clean already-updated no-op (0 changes, all current); otherwise require
        # exactly 3 staged changes before any commit.
        if total_changes == 0 and already_current == len(_TARGET_WORKFLOWS):
            print("\nNO-OP: all 3 compile_proposal prompts already current — nothing to apply.")
            await db.rollback()
            return 0

        if total_changes != _EXPECTED_CHANGES:
            print(
                f"\nABORT: expected exactly {_EXPECTED_CHANGES} changes, got {total_changes} "
                "— rolling back."
            )
            await db.rollback()
            return 3

        if apply:
            await db.commit()
            print(f"\nCOMMITTED: {total_changes} compile_proposal prompt fields updated.")
            await _verify(db)
        else:
            await db.rollback()
            print("\nDRY-RUN complete: rolled back, no DB changes.")

    return 0


async def _verify(db) -> None:
    """Post-apply drift re-check (read-only)."""
    print("\n=== post-apply verification ===")
    wfs = (
        (await db.execute(select(Workflow).where(Workflow.name.in_(_TARGET_WORKFLOWS))))
        .scalars()
        .all()
    )
    updated = 0
    stale = 0
    for wf in wfs:
        definition = wf.definition_json or {}
        step = next(
            (s for s in definition.get("steps", []) if s.get("key") == _STEP_KEY), None
        )
        prompt = (step or {}).get("config", {}).get("prompt", "") if step else ""
        v, i, r = _flags(prompt)
        ok = v and i and r
        updated += 1 if ok else 0
        stale += 0 if ok else 1
        print(f"  {definition.get('name')}: tokens+rules_present={ok} len={len(prompt)}")
    print(f"  compile_proposal updated: {updated}/{len(wfs)}  stale remaining: {stale}")


if __name__ == "__main__":
    _apply = "--apply" in sys.argv
    raise SystemExit(asyncio.run(main(_apply)))
