"""Phase 6.8.C — Targeted HAWK system_prompt DB propagation.

Updates ONLY the ``system_prompt`` column for the three HAWK agent_configs rows
(hawk_trend, hawk_structure, hawk_counter).  Every other column — runtime_kind,
model, max_tokens, temperature, fallback_chain, tools_config, is_active,
memory_type, context_window_size — is left byte-for-byte identical.

No workflow definitions are touched.  No schedules are touched.  No runtime
profile is changed.  No run or order is triggered.

Usage:
    uv run python apply_hawk_system_prompt_update.py            # dry-run (no commit)
    uv run python apply_hawk_system_prompt_update.py --apply    # commit the 3 updates
"""

from __future__ import annotations

import asyncio
import re
import sys

from sqlalchemy import select

from app.commands.seed_crypto_workflow import (
    _HAWK_COUNTER_PROMPT,
    _HAWK_STRUCTURE_PROMPT,
    _HAWK_TREND_PROMPT,
)
from app.db.models.project import AgentConfig, Project
from app.db.session import async_session_maker

_HAWK_ROLES = {"hawk_trend", "hawk_structure", "hawk_counter"}

_NEW_PROMPTS: dict[str, str] = {
    "hawk_trend": _HAWK_TREND_PROMPT,
    "hawk_structure": _HAWK_STRUCTURE_PROMPT,
    "hawk_counter": _HAWK_COUNTER_PROMPT,
}

# Stale top-level keys that should no longer appear in OUTPUT FORMAT
_STALE_KEYS: dict[str, list[str]] = {
    "hawk_trend": ["trend_direction", "ema_alignment", "price_structure", "macd_signal"],
    "hawk_structure": [
        "price_vs_vwap",
        "structure_assessment",
        "active_order_block",
        "nearest_support_levels",
        "nearest_resistance_levels",
    ],
    "hawk_counter": [
        "rsi_4h",
        "rsi_signal",
        "rsi_divergence",
        "funding_rate",
        "funding_signal",
        "long_short_ratio",
        "crowd_positioning",
        "counter_signals_found",
    ],
}

# Nested assessment keys expected in each new prompt's OUTPUT FORMAT
_NESTED_ASSESSMENT_KEYS: dict[str, str] = {
    "hawk_trend": "trend_assessment",
    "hawk_structure": "structure_assessment",
    "hawk_counter": "counter_assessment",
}


def _extract_output_format_block(prompt: str) -> str:
    """Extract the OUTPUT FORMAT JSON block from a prompt."""
    m = re.search(r"OUTPUT FORMAT[^\n]*\n(\{.*?\})\n\nNever output", prompt, re.DOTALL)
    return m.group(0) if m else ""


def _has_top_level_key(block: str, key: str) -> bool:
    return bool(re.search(rf'^\s{{2}}"{re.escape(key)}":', block, re.MULTILINE))


def _check_stale_keys(role: str, prompt: str) -> list[str]:
    block = _extract_output_format_block(prompt)
    return [k for k in _STALE_KEYS[role] if _has_top_level_key(block, k)]


def _check_forbidden_block(prompt: str) -> bool:
    return bool(re.search(r"FORBIDDEN top-level keys", prompt))


def _check_nested_assessment(role: str, prompt: str) -> bool:
    key = _NESTED_ASSESSMENT_KEYS[role]
    block = _extract_output_format_block(prompt)
    return key in block


def _print_row_report(label: str, role: str, row: AgentConfig, new_prompt: str) -> None:
    cur = row.system_prompt or ""
    stale_in_current = _check_stale_keys(role, cur)
    stale_in_new = _check_stale_keys(role, new_prompt)
    forbidden_in_new = _check_forbidden_block(new_prompt)
    nested_in_new = _check_nested_assessment(role, new_prompt)

    print(f"\n  [{label}]")
    print(f"    id               : {row.id}")
    print(f"    name             : {row.name}")
    print(f"    role             : {row.role}")
    print(f"    project_id       : {row.project_id}")
    print(f"    current_len      : {len(cur)}")
    print(f"    new_len          : {len(new_prompt)}")
    print(f"    prompt_differs   : {cur != new_prompt}")
    print(f"    stale_keys_current (OUTPUT FORMAT top-level): {stale_in_current or 'none'}")
    print(f"    stale_keys_new   : {stale_in_new or 'none (clean)'}")
    print(f"    forbidden_block_in_new   : {forbidden_in_new}")
    print(f"    nested_assessment_in_new : {nested_in_new}  ({_NESTED_ASSESSMENT_KEYS[role]})")
    print(f"    runtime_kind     : {row.runtime_kind}  [UNCHANGED]")
    print(f"    model            : {row.model}  [UNCHANGED]")
    print(f"    max_tokens       : {row.max_tokens}  [UNCHANGED]")


async def main(apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"\n=== Phase 6.8.C — HAWK system_prompt DB propagation [{mode}] ===")
    print("Scope: ONLY agent_configs.system_prompt for hawk_trend / hawk_structure / hawk_counter")
    print("No workflow, schedule, runtime profile, model, or execution changes.\n")

    # Sanity-check new prompts before touching DB
    for role in _HAWK_ROLES:
        stale = _check_stale_keys(role, _NEW_PROMPTS[role])
        if stale:
            print(f"ABORT: new {role} prompt still has stale top-level keys: {stale}")
            return 1
        if not _check_forbidden_block(_NEW_PROMPTS[role]):
            print(f"ABORT: new {role} prompt is missing the FORBIDDEN block")
            return 1
        if not _check_nested_assessment(role, _NEW_PROMPTS[role]):
            print(f"ABORT: new {role} prompt is missing reasoning.{_NESTED_ASSESSMENT_KEYS[role]}")
            return 1
    print("[pre-flight] New prompt constants pass all schema checks.\n")

    async with async_session_maker() as db:
        # Query ALL hawk agent_config rows (may span multiple projects)
        rows = (
            (
                await db.execute(
                    select(AgentConfig).where(AgentConfig.role.in_(_HAWK_ROLES))
                )
            )
            .scalars()
            .all()
        )

        if not rows:
            print("ABORT: no agent_config rows found with HAWK roles.")
            return 1

        # Group by project
        projects_seen: dict[str, list[AgentConfig]] = {}
        for row in rows:
            pid = str(row.project_id)
            projects_seen.setdefault(pid, []).append(row)

        print(f"Found {len(rows)} HAWK agent_config row(s) across {len(projects_seen)} project(s).")

        # Lookup project names
        for pid, agents in projects_seen.items():
            from uuid import UUID
            proj = await db.get(Project, UUID(pid))
            pname = proj.name if proj else "(unknown)"
            print(f"\nProject: {pname}  [{pid}]")
            print(f"  HAWK rows in this project: {[a.role for a in agents]}")
            for agent in agents:
                _print_row_report(agent.role, agent.role, agent, _NEW_PROMPTS[agent.role])

        # Safety: must be exactly 3 rows (one per hawk role) across all projects
        # OR exactly 3 rows in a single project. Confirm with user if > 3.
        if len(rows) != 3:
            print(
                f"\nWARNING: Expected exactly 3 HAWK rows, found {len(rows)}. "
                f"Roles found: {[r.role for r in rows]}"
            )
            if len(rows) > 3:
                print("ABORT: ambiguous — more than one project has HAWK agents.")
                print("Run with a project-scoped argument (not yet implemented) or clean up duplicates.")
                await db.rollback()
                return 1

        # Confirm no non-HAWK agents are in the update set
        non_hawk = [r for r in rows if r.role not in _HAWK_ROLES]
        if non_hawk:
            print(f"ABORT: non-HAWK rows matched: {[r.role for r in non_hawk]}")
            await db.rollback()
            return 1

        # Confirm all 3 roles present
        roles_found = {r.role for r in rows}
        missing_roles = _HAWK_ROLES - roles_found
        if missing_roles:
            print(f"ABORT: missing HAWK role(s): {missing_roles}")
            await db.rollback()
            return 1

        print(f"\n--- Dry-run summary ---")
        changes = [(r, _NEW_PROMPTS[r.role]) for r in rows if r.system_prompt != _NEW_PROMPTS[r.role]]
        already_current = [r for r in rows if r.system_prompt == _NEW_PROMPTS[r.role]]
        print(f"  Rows that need updating   : {len(changes)}")
        print(f"  Rows already up-to-date   : {len(already_current)}")
        for r in already_current:
            print(f"    - {r.role}: already matches new prompt (no-op)")

        if not changes:
            print("\nAll HAWK system_prompts already match the Phase 6.8 constants. Nothing to do.")
            await db.rollback()
            return 0

        if not apply:
            print(f"\nDRY-RUN complete. Pass --apply to commit {len(changes)} update(s).")
            await db.rollback()
            return 0

        # === APPLY ===
        print(f"\nApplying {len(changes)} system_prompt update(s)...")
        updated = []
        for row, new_prompt in changes:
            row.system_prompt = new_prompt
            updated.append(row.role)

        await db.flush()
        await db.commit()

        print(f"\nCOMMITTED: {len(updated)} HAWK system_prompt(s) updated: {updated}")

        # Post-update verification (re-query)
        rows_after = (
            (
                await db.execute(
                    select(AgentConfig).where(AgentConfig.role.in_(_HAWK_ROLES))
                )
            )
            .scalars()
            .all()
        )
        print("\n--- Post-update verification ---")
        all_ok = True
        for row in rows_after:
            sp = row.system_prompt or ""
            stale = _check_stale_keys(row.role, sp)
            has_forbidden = _check_forbidden_block(sp)
            has_nested = _check_nested_assessment(row.role, sp)
            status = "OK" if (not stale and has_forbidden and has_nested) else "FAIL"
            if status != "OK":
                all_ok = False
            print(
                f"  {row.role}: len={len(sp)} stale_keys={stale or 'none'} "
                f"forbidden_block={has_forbidden} nested_assessment={has_nested} [{status}]"
            )
        if all_ok:
            print("\nAll 3 HAWK rows verified clean. DB propagation successful.")
        else:
            print("\nWARNING: One or more rows failed post-update verification.")
            return 1

    return 0


if __name__ == "__main__":
    _apply = "--apply" in sys.argv
    raise SystemExit(asyncio.run(main(_apply)))
