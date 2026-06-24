"""Phase 6.14.M — Targeted update of compile_proposal prompt in workflow definition_json.

Updates only the config.prompt of the compile_proposal step in three workflows:
  - Crypto Trade Pipeline — Proposal to Execution
  - Crypto Trade Pipeline — Auto 30m
  - Crypto Trade Pipeline — Auto 15m

Does NOT modify any other step, gate config, topology, schedule, or agent config.
"""

from __future__ import annotations

import asyncio
import json
import sys

import asyncpg

PROJECT_ID = "288bc95a-b4da-46e7-bdfa-b5630233f586"

_DIRECTIONAL_RULES = (
    "MAJORITY DIRECTION INVARIANT (mandatory — code hard-blocks any mismatch): "
    "The HAWK vote majority_direction in $hawk_vote_result determines the ONLY permitted trade direction. "
    "BULLISH majority → proposal.direction MUST be LONG. "
    "BEARISH majority → proposal.direction MUST be SHORT. "
    "NEUTRAL or NO_MAJORITY → return approval_status=BLOCKED (no_trade), do NOT produce a directional proposal. "
    "You MUST NOT choose the minority HAWK direction. You MUST NOT override the majority. "
    "If you cannot produce a valid proposal in the majority direction, return approval_status=BLOCKED (no_trade). "
    "DIRECTIONAL SL/TP INVARIANT (mandatory — the proposal is hard-rejected by code if violated): "
    "For LONG: stop_loss < entry; every take_profit > entry; take_profit levels must ascend. "
    "For SHORT: stop_loss > entry; every take_profit < entry; take_profit levels must descend. "
    "HAWK INVALIDATION LEVELS: select stop_loss from, or justify it against, the provided "
    "$hawk_invalidation_levels above. A buffer-adjusted stop is acceptable ONLY if it stays on the "
    "correct side of entry (SHORT: strictly above entry; LONG: strictly below entry). Do NOT "
    "fabricate a stop_loss that ignores the HAWK invalidation levels. If no valid directional "
    "stop_loss can be produced, return approval_status=BLOCKED (no_trade) instead of inventing one. "
)

_OUTPUT_FORMAT = (
    "OUTPUT FORMAT (mandatory): return the raw JSON object only. "
    "Do NOT wrap in markdown code fences or triple backticks. "
    "Do NOT include explanation text before or after the JSON. "
    "Output must begin with { and end with }."
)

MANUAL_PROMPT = (
    "Compile the prior crypto analysis into a final trade proposal. "
    "Use the workflow memory plus this input payload: $input_payload. "
    "RUNTIME MARKET TYPE — MANDATORY (emit this exact value in output.market_type): $market_type. "
    "HAWK vote summary (majority direction + per-HAWK outputs): $hawk_vote_result. "
    "Pre-extracted, Python-verified HAWK invalidation levels: $hawk_invalidation_levels. "
    + _DIRECTIONAL_RULES
    + "The proposal must satisfy code Kill Switch rules: TP1 actual RR >= 2.0, "
    "position_size_usdt must be >= 50.0 USDT for futures (exchange minimum — code hard-rejects below this), "
    "or >= 40.0 for spot paper mode (4% of PAPER_PORTFOLIO_USDT=1000). "
    "Do NOT use 40.0 for futures. Use exactly 50.0 if risk settings allow, "
    "and every numeric field must be mathematically consistent. "
    + _OUTPUT_FORMAT
)

AUTO_PROMPT = (
    "Compile the prior crypto analysis into a final trade proposal. "
    "Use the workflow memory plus this input payload: $input_payload. "
    "RUNTIME MARKET TYPE — MANDATORY (emit this exact value in output.market_type): $market_type. "
    "Market data context: $market_data. "
    "HAWK vote summary (majority direction + per-HAWK outputs): $hawk_vote_result. "
    "Pre-extracted, Python-verified HAWK invalidation levels: $hawk_invalidation_levels. "
    + _DIRECTIONAL_RULES
    + "The proposal must satisfy code Kill Switch rules: TP1 actual RR >= 2.0, "
    "position_size_usdt must be >= 50.0 USDT for futures (exchange minimum — code hard-rejects below this), "
    "or >= 40.0 for spot paper mode (4% of PAPER_PORTFOLIO_USDT=1000). "
    "Do NOT use 40.0 for futures. Use exactly 50.0 if risk settings allow, "
    "and every numeric field must be mathematically consistent. "
    "Set approval_status to PENDING_APPROVAL. "
    + _OUTPUT_FORMAT
)

TARGET_WORKFLOWS: dict[str, str] = {
    "Crypto Trade Pipeline — Proposal to Execution": MANUAL_PROMPT,
    "Crypto Trade Pipeline — Auto 30m": AUTO_PROMPT,
    "Crypto Trade Pipeline — Auto 15m": AUTO_PROMPT,
}


async def main() -> None:
    conn = await asyncpg.connect(
        "postgresql://postgres:postgres@db:5432/pixel_dream_agent"
    )
    try:
        for wf_name, new_prompt in TARGET_WORKFLOWS.items():
            row = await conn.fetchrow(
                "SELECT id, definition_json FROM workflows WHERE project_id = $1 AND name = $2",
                PROJECT_ID,
                wf_name,
            )
            if not row:
                print(f"[SKIP] Workflow not found: {wf_name!r}", flush=True)
                continue

            wf_id = row["id"]
            definition = json.loads(row["definition_json"])
            steps = definition.get("steps", [])

            updated = False
            for step in steps:
                if step.get("key") == "compile_proposal":
                    config = step.setdefault("config", {})
                    old_prompt = config.get("prompt", "")
                    if old_prompt == new_prompt:
                        print(f"[SKIP] {wf_name!r} — compile_proposal prompt already current", flush=True)
                        updated = True
                        break
                    config["prompt"] = new_prompt
                    updated = True
                    print(f"[UPDATE] {wf_name!r} — compile_proposal prompt updated", flush=True)
                    print(f"  OLD ends: ...{old_prompt[-80:]!r}", flush=True)
                    print(f"  NEW ends: ...{new_prompt[-80:]!r}", flush=True)
                    break

            if not updated:
                print(f"[WARN] compile_proposal step not found in {wf_name!r}", flush=True)
                continue

            await conn.execute(
                "UPDATE workflows SET definition_json = $1::jsonb WHERE id = $2",
                json.dumps(definition),
                wf_id,
            )

        print("\n[DONE] All targeted updates complete.", flush=True)

        # Verification read-back
        print("\n--- VERIFICATION ---", flush=True)
        for wf_name in TARGET_WORKFLOWS:
            row = await conn.fetchrow(
                "SELECT definition_json FROM workflows WHERE project_id = $1 AND name = $2",
                PROJECT_ID,
                wf_name,
            )
            if not row:
                print(f"[ERROR] {wf_name!r} not found on read-back", flush=True)
                continue
            definition = json.loads(row["definition_json"])
            for step in definition.get("steps", []):
                if step.get("key") == "compile_proposal":
                    prompt = step.get("config", {}).get("prompt", "")
                    has_output_format = "OUTPUT FORMAT (mandatory)" in prompt
                    has_no_fence = "Do NOT wrap in markdown code fences" in prompt
                    has_no_explanation = "Do NOT include explanation text" in prompt
                    has_brace = "Output must begin with { and end with }." in prompt
                    has_stale = prompt.endswith("Return strict JSON only.")
                    has_50_usdt = "50.0 USDT for futures" in prompt
                    has_no_40 = "Do NOT use 40.0 for futures" in prompt
                    print(
                        f"{wf_name!r}: output_format={has_output_format} no_fence={has_no_fence} "
                        f"no_explanation={has_no_explanation} brace_bound={has_brace} "
                        f"stale_ending={has_stale} has_50usdt={has_50_usdt} no_40={has_no_40}",
                        flush=True,
                    )
                    break

    finally:
        await conn.close()


asyncio.run(main())
