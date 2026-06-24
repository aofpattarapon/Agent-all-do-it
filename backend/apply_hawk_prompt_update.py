"""Targeted HAWK prompt-only DB update.

Replaces ONLY the ``config.prompt`` field of the hawk_trend / hawk_structure /
hawk_counter steps in three crypto trade pipeline workflows, swapping the legacy
``$market_data`` template for the current ``$market_data_hawk`` template pulled
from the code prompt map.

Everything else in ``definition_json`` is left byte-for-byte identical: nodes,
edges, version, agent_key UUIDs, trigger/schedule, non-HAWK step prompts, and
all other step config keys.

Usage:
    uv run python apply_hawk_prompt_update.py            # dry-run (no commit)
    uv run python apply_hawk_prompt_update.py --apply    # commit the 9 updates
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
_HAWK_KEYS = {"hawk_trend", "hawk_structure", "hawk_counter"}
_LEGACY_TOKEN = "$market_data"
_NEW_TOKEN = "$market_data_hawk"


def _topology_fingerprint(definition: dict) -> dict:
    """Everything that must NOT change: nodes, edges, version, trigger, and for
    every step its agent_key + kind + key + all config keys EXCEPT the HAWK
    prompt we intend to edit. Non-HAWK prompts ARE included here so any change
    to them is caught as a violation."""
    steps_fp = []
    for step in definition.get("steps", []):
        key = step.get("key", "")
        config = dict(step.get("config") or {})
        if key in _HAWK_KEYS:
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


async def main(apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== HAWK prompt-only update [{mode}] ===\n")

    total_changes = 0
    nonhawk_violations = 0
    topology_violations = 0

    async with async_session_maker() as db:
        workflows = (
            (await db.execute(select(Workflow).where(Workflow.name.in_(_TARGET_WORKFLOWS))))
            .scalars()
            .all()
        )
        found_names = {wf.name for wf in workflows}
        missing = _TARGET_WORKFLOWS - found_names
        if missing:
            print(f"WARNING: target workflow(s) not found: {sorted(missing)}\n")

        for wf in workflows:
            old_def = wf.definition_json or {}
            name = old_def.get("name") or wf.name
            prompt_map = _workflow_prompt_map(name)
            if not prompt_map:
                print(f"SKIP {name}: no prompt map (not a recognized pipeline)\n")
                continue

            new_def = copy.deepcopy(old_def)
            before_fp = _topology_fingerprint(old_def)

            print(f"Workflow: {name}  [{wf.id}]")
            for step in new_def.get("steps", []):
                key = step.get("key", "")
                if key not in _HAWK_KEYS:
                    continue
                config = step.get("config") or {}
                old_prompt = config.get("prompt") or ""
                new_prompt = prompt_map.get(key, "")
                if not new_prompt:
                    print(f"  ! {key}: no template in prompt map — skipped")
                    continue
                old_has_legacy = _LEGACY_TOKEN in old_prompt and _NEW_TOKEN not in old_prompt
                new_has_hawk = _NEW_TOKEN in new_prompt
                print(
                    f"  - {key}: old_len={len(old_prompt)} new_len={len(new_prompt)} "
                    f"old_has_$market_data={old_has_legacy} new_has_$market_data_hawk={new_has_hawk}"
                )
                if old_prompt != new_prompt:
                    config["prompt"] = new_prompt
                    step["config"] = config
                    total_changes += 1

            # Integrity check: nothing but HAWK prompts may differ.
            after_fp = _topology_fingerprint(new_def)
            if before_fp != after_fp:
                topology_violations += 1
                print("  !! TOPOLOGY/NON-HAWK VIOLATION DETECTED — aborting this workflow")
                # Identify which non-HAWK step changed (defensive)
                for b, a in zip(before_fp["steps"], after_fp["steps"], strict=False):
                    if b != a:
                        print(f"     changed step fingerprint: {b.get('key')}")
                        nonhawk_violations += 1
                continue

            if apply:
                wf.definition_json = new_def  # reassign whole object → marks JSONB dirty
            print()

        print("---")
        print(f"Total HAWK prompt changes staged: {total_changes}")
        print(f"Non-HAWK violations: {nonhawk_violations}")
        print(f"Topology violations: {topology_violations}")

        if topology_violations or nonhawk_violations:
            print("\nABORT: integrity violation — rolling back, nothing committed.")
            await db.rollback()
            return 2

        if total_changes != 9:
            print(f"\nABORT: expected exactly 9 changes, got {total_changes} — rolling back.")
            await db.rollback()
            return 3

        if apply:
            await db.commit()
            print("\nCOMMITTED: 9 HAWK prompt fields updated.")
        else:
            await db.rollback()
            print("\nDRY-RUN complete: rolled back, no DB changes.")

    return 0


if __name__ == "__main__":
    _apply = "--apply" in sys.argv
    raise SystemExit(asyncio.run(main(_apply)))
