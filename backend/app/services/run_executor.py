"""Real workflow execution engine.

Loads a queued :class:`Run`, walks its workflow's ``definition_json["steps"]``,
dispatches each step to a runtime adapter (or knowledge/approval handler),
streams events to the in-memory event bus + room hub, and persists step output.

Quota / rate-limit / transient errors pause the run (with ``retry_after_at``)
instead of failing it, so a recovery worker can resume later. Auth errors pause
with ``resume_policy="manual_token_fix"``.
"""

import asyncio
import contextlib
import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.http_request import http_get, http_post
from app.core.exceptions import NotFoundError
from app.core.json_utils import extract_json_object
from app.db.models.project import AgentConfig
from app.db.models.workflow import Run, RunStep
from app.repositories import (
    agent_config_repo,
    knowledge_repo,
    project_repo,
    run_repo,
    workflow_repo,
)
from app.services.context_compaction import ContextCompactionService
from app.services.cost_guard import CostGuard
from app.services.crypto_handoff_validator import (
    normalize_compile_proposal_approval_status,
    validate_step_output,
)
from app.services.crypto_persistence import CryptoPersistenceService, build_trade_journal_raw_facts
from app.services.dna_memory import DNAMemoryService
from app.services.event_bus import AgentEvent, event_bus
from app.services.execution_preflight import (
    ExecutionPlan,
    ExecutionPreflightError,
    entry_price_from_plan,
    prepare_execution_plan,
    take_profit_levels_from_proposal,
)
from app.services.handoff_contracts import contracts_for_handoff, validate_handoff
from app.services.hawk_output_repair import (
    assess_hawk_output_reliability,
    build_hawk_repair_prompt,
    format_hawk_block_details,
    repair_hawk_output,
)
from app.services.llm_error_classifier import LLMErrorInfo, classify_llm_error
from app.services.market_data_renderer import render_market_data_for_hawk
from app.services.metrics_tracker import MetricsTracker
from app.services.model_fallback import run_with_fallback
from app.services.obsidian_exporter import export_step as obsidian_export
from app.services.prompt_registry import PromptRegistryService
from app.services.trace_emitter import TraceEmitter
from app.services.trading_mode import effective_project_mode, resolve_trading_mode
from app.services.warmup_policy import (
    DEFAULT_WARMUP_MODE,
    decide_warmup_action,
    resolve_warmup_mode,
)

logger = logging.getLogger(__name__)

# Step keys that are HAWK analysis agents — used for retry and context tracking.
_HAWK_STEP_KEYS: frozenset[str] = frozenset({"hawk_trend", "hawk_structure", "hawk_counter"})


def _hawk_levels_from_context(context: dict) -> list[float]:
    """Parse the numeric HAWK invalidation levels stashed in context after the vote gate.

    context['hawk_invalidation_levels'] is a JSON string (dict role->level) but tolerate a
    raw dict/list too. Always returns a list of floats (empty if absent/malformed).
    """
    raw = context.get("hawk_invalidation_levels")
    if not raw:
        return []
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    values = obj.values() if isinstance(obj, dict) else (obj or [])
    levels: list[float] = []
    for v in values:
        try:
            levels.append(float(v))
        except (TypeError, ValueError):
            continue
    return levels


def compile_proposal_observability(output: str, template: str, context: dict) -> dict:
    """Build read-only observability metadata for a compile_proposal (trade_proposal) step.

    Returns booleans/scalars only — never raw payloads or secrets. Side-validity is classified
    by reusing the deterministic ``validate_directional_risk_levels`` so this stays in lock-step
    with the hard validator WITHOUT changing any pass/fail behavior.

    stop_loss is considered matched-or-justified against the HAWK levels when it equals a level
    (within a 0.1% tolerance) OR sits on the correct side of entry within the HAWK-justified zone
    (a small buffer beyond the most extreme level). Exact equality is intentionally NOT required.
    """
    from app.services.execution_preflight import validate_directional_risk_levels

    parsed = extract_json_object(output) or {}
    direction = str(parsed.get("direction") or "").upper()
    entry = entry_price_from_plan(parsed.get("entry_plan"))

    sl_raw = parsed.get("stop_loss")
    try:
        stop_loss = float(sl_raw) if sl_raw is not None else None
    except (TypeError, ValueError):
        stop_loss = None

    tps: list[float] = []
    for tp in parsed.get("take_profit") or []:
        val = tp.get("tp_level") if isinstance(tp, dict) else tp
        try:
            tps.append(float(val))
        except (TypeError, ValueError):
            continue

    if direction in {"LONG", "SHORT"}:
        errs = validate_directional_risk_levels(direction, entry, stop_loss, tps)
        sl_side_valid = stop_loss is not None and not any("stop_loss" in e for e in errs)
        tp_side_valid = bool(tps) and not any("take_profit" in e for e in errs)
    else:
        sl_side_valid = False
        tp_side_valid = False

    hawk_levels = _hawk_levels_from_context(context)

    matched_or_justified = False
    if stop_loss is not None and hawk_levels:
        tol = abs(entry) * 0.001 if entry else 0.0
        matched = any(abs(stop_loss - lvl) <= tol for lvl in hawk_levels)
        justified = False
        if sl_side_valid and entry > 0:
            if direction == "SHORT":
                justified = entry < stop_loss <= max(hawk_levels) * 1.01
            elif direction == "LONG":
                justified = min(hawk_levels) * 0.99 <= stop_loss < entry
        matched_or_justified = bool(matched or justified)

    # Phase 3: majority-direction alignment observability (scalars/booleans only).
    majority_direction = str(context.get("majority_direction") or "").upper() or None
    _md_map = {"BULLISH": "LONG", "BEARISH": "SHORT"}
    expected_direction: str | None = (
        _md_map.get(majority_direction or "") if majority_direction else None
    )
    actual_direction: str | None = direction or None
    direction_majority_aligned: bool | None = None
    majority_alignment_block_reason: str | None = None
    if majority_direction and majority_direction not in ("NEUTRAL", "NO_MAJORITY"):
        if expected_direction is not None and actual_direction is not None:
            direction_majority_aligned = actual_direction == expected_direction
            if not direction_majority_aligned:
                majority_alignment_block_reason = "direction_majority_mismatch"
    elif majority_direction in ("NEUTRAL", "NO_MAJORITY"):
        direction_majority_aligned = False
        majority_alignment_block_reason = "majority_direction_unavailable"

    vote_tally = context.get("vote_tally")
    vote_tally_str: str | None = None
    if isinstance(vote_tally, dict) and vote_tally:
        vote_tally_str = str(vote_tally)

    return {
        "direction": direction or None,
        "reference_price": entry or None,
        "stop_loss": stop_loss,
        "stop_loss_side_valid": sl_side_valid,
        "take_profit_side_valid": tp_side_valid,
        "stop_loss_matched_or_justified_against_hawk_level": matched_or_justified,
        "hawk_invalidation_levels_present": bool(hawk_levels),
        "prompt_contained_hawk_invalidation_levels": "$hawk_invalidation_levels" in template,
        "prompt_contained_directional_rules": "DIRECTIONAL SL/TP INVARIANT" in template,
        "prompt_contained_majority_invariant": "MAJORITY DIRECTION INVARIANT" in template,
        # Phase 3: majority alignment
        "hawk_majority_direction": majority_direction,
        "expected_proposal_direction": expected_direction,
        "actual_proposal_direction": actual_direction,
        "direction_majority_aligned": direction_majority_aligned,
        "majority_alignment_block_reason": majority_alignment_block_reason,
        "vote_tally": vote_tally_str,
    }


# Max nesting for sub_workflow steps. A self- or cyclic sub_workflow would otherwise
# recurse until the Celery hard kill, leaving the run stuck 'running' (a permanent jam).
_MAX_SUB_WORKFLOW_DEPTH = 5


def _extract_pnl_pct(text: str) -> float | None:
    """Extract realized PnL% from journal/execution output. Returns None if not found."""
    import re

    for pat in (r'"pnl_pct"\s*:\s*(-?[\d.]+)', r"pnl[_%\s]+(-?[\d.]+)%", r"realized.*?(-?[\d.]+)%"):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


def _extract_sage_veto(text: str) -> tuple[bool, str]:
    """Return (is_vetoed, veto_reason) from a SAGE output string."""
    payload = extract_json_object(text)
    if not isinstance(payload, dict):
        return False, ""
    decision = str(payload.get("sage_decision") or "").upper()
    if decision != "VETOED":
        return False, ""
    reason = str(payload.get("veto_reason") or payload.get("risk_notes") or "SAGE veto")
    if isinstance(payload.get("risk_notes"), list):
        reason = "; ".join(str(r) for r in payload["risk_notes"])
    return True, reason


def _extract_auto_trade_confidence(text: str) -> int:
    """Parse confidence_score from SAGE/proposal output. Returns 0 if not found."""
    import re

    # Try JSON field first
    for pattern in (
        r'"confidence_score"\s*:\s*(\d+)',
        r'"confidence"\s*:\s*(\d+)',
        r"confidence[_\s]score[:\s]+(\d+)",
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return min(int(m.group(1)), 100)
    return 0


class RunExecutor:
    def __init__(
        self,
        db: AsyncSession,
        *,
        _depth: int = 0,
        _visited_workflows: set[UUID] | None = None,
    ) -> None:
        self.db = db
        self.tracer = TraceEmitter(db)
        self.metrics = MetricsTracker(db)
        # Sub-workflow recursion guards (see _run_sub_workflow). Each executor gets its
        # own copy of the visited set so mutation never leaks across runs.
        self._depth = _depth
        self._visited_workflows: set[UUID] = set(_visited_workflows or ())

    # ── Public API ──────────────────────────────────────────────────────────

    async def execute(self, run_id: UUID, project_id: UUID) -> Run:
        run = await self._load_run(run_id, project_id)
        # Track this run's workflow so a nested sub_workflow that points back here
        # (directly or via a cycle) is rejected by _run_sub_workflow's cycle guard.
        if run.workflow_id is not None:
            self._visited_workflows.add(run.workflow_id)
        project = await project_repo.get_by_id(self.db, project_id)
        project_name = project.name if project else ""
        project_slug = (project.slug if project else "") or ""

        workflow_definition = await self._load_workflow_definition(run)
        steps = self._steps_from_definition(workflow_definition)
        validation_only = self._validation_only_config(
            workflow_definition, run.input_payload_json or {}
        )
        trace_id = self._trace_id(run)

        _mode = resolve_trading_mode()
        if _mode.conflict:
            logger.warning(
                "[%s] run_start mode_conflict: %s",
                self._htrace(run_id),
                _mode.conflict,
            )
        else:
            logger.info(
                "[%s] run_start exchange_mode=%s trading_mode=%s is_live=%s "
                "is_order_capable=%s is_local_simulation=%s venue=%s",
                self._htrace(run_id),
                _mode.exchange_mode,
                _mode.trading_mode,
                _mode.is_live,
                _mode.is_order_capable,
                _mode.is_local_simulation,
                "local_simulation"
                if _mode.is_local_simulation
                else f"binance_{_mode.exchange_mode}",
            )

        run.status = "running"
        if run.started_at is None:
            run.started_at = datetime.now(UTC)
        run.error_text = ""
        run.pause_reason = ""
        await run_repo.update_run(self.db, db_run=run, update_data={})
        await self.db.commit()

        try:
            await self.metrics.start_run(run_id, project_id)
        except Exception as exc:
            logger.warning("MetricsTracker.start_run failed: %s", exc)

        await self.tracer.emit(
            event_type="run.started",
            project_id=project_id,
            run_id=run_id,
            trace_id=trace_id,
            summary=f"Run started ({len(steps)} steps)",
            event_status="running",
        )
        await self._emit(
            project_id,
            run_id,
            "run.started",
            agent_name="orchestrator",
            data=f"Run started with {len(steps)} steps",
        )

        # Restore last_output from prior steps when resuming mid-run.
        context: dict = {
            "last_output": await self._last_completed_output(run),
            "input_payload": run.input_payload_json or {},
            "project_name": project_name,
            "project_slug": project_slug,
            "market_type": os.getenv("MARKET_TYPE", "futures").lower(),
            "run_id": str(run_id),
        }

        start_time = time.monotonic()
        total_tokens = 0

        idx = run.current_step_index or 0
        while idx < len(steps):
            step_def = steps[idx]
            step_key = str(step_def.get("key") or f"step_{idx + 1}")
            step_kind = str(step_def.get("kind") or "prompt")
            config = step_def.get("config") or {}

            db_step = await self._get_or_create_step(run, step_key, step_kind, step_def)
            db_step.status = "running"
            db_step.started_at = datetime.now(UTC)
            await run_repo.update_run_step(self.db, db_step=db_step, update_data={})

            await self.tracer.emit(
                event_type="step.started",
                project_id=project_id,
                run_id=run_id,
                trace_id=trace_id,
                summary=f"{step_key} ({step_kind})",
                event_status="running",
            )
            await self._emit(
                project_id,
                run_id,
                "run.step_started",
                agent_name=step_key,
                data=f"{step_kind} started",
            )

            # ── Auto-trade gate: auto-approve when confidence >= threshold ──
            if step_kind == "auto_trade_gate":
                threshold = int((config or {}).get("confidence_threshold", 90))
                last_out = context.get("last_output", "")
                confidence = _extract_auto_trade_confidence(last_out)
                if confidence >= threshold:
                    db_step.status = "completed"
                    db_step.output_text = f"AUTO_APPROVED (confidence={confidence} >= {threshold})"
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    skip_count = int((config or {}).get("skip_steps_on_auto", 1))
                    idx += skip_count  # skip the human_approval_gate step
                    context["auto_trade_approved"] = True
                    context["auto_trade_confidence"] = confidence
                    await self._emit(
                        project_id,
                        run_id,
                        "run.step_completed",
                        agent_name=step_key,
                        data=f"Auto-approved (confidence={confidence}≥{threshold})",
                    )
                    idx += 1
                    run.current_step_index = idx
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    continue
                else:
                    # Fall through to human approval: treat as approval gate
                    db_step.status = "waiting_approval"
                    run.status = "waiting_approval"
                    run.current_step_index = idx
                    run.paused_at = datetime.now(UTC)
                    run.pause_reason = "approval"
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    await self.db.commit()
                    await self._emit(
                        project_id,
                        run_id,
                        "run.waiting_approval",
                        agent_name=step_key,
                        data=f"Confidence={confidence}<{threshold}: awaiting human approval",
                    )
                    return run

            # ── Winrate auto-trade gate (auto-30m mode: no human approval) ──
            if step_kind == "winrate_trade_gate":
                from app.core.config import settings as _settings

                threshold = float(
                    (config or {}).get("winrate_threshold", _settings.PIPELINE_WINRATE_THRESHOLD)
                )
                warmup_trades = int(
                    (config or {}).get("warmup_trades", _settings.PIPELINE_WARMUP_TRADES)
                )
                below_threshold_action = str((config or {}).get("below_threshold", "pause"))

                svc = CryptoPersistenceService(self.db)
                winrate = await svc.get_project_winrate(project_id)
                closed_count = await svc.get_closed_trade_count(project_id)

                # One-open-position cap — never stack trades on the same symbol.
                # Resolve the symbol explicitly; never silently fall back to a default coin.
                symbol = ((context.get("input_payload") or {}).get("symbol") or "").strip().upper()
                if not symbol:
                    raise ValueError("winrate_trade_gate: symbol missing from input_payload")
                if await svc.has_open_position(project_id, symbol):
                    skip_reason = f"SKIPPED: open position already exists for {symbol}"
                    db_step.status = "completed"
                    db_step.output_json = {
                        "output": skip_reason,
                        "meta": {"skip_reason": "open_position"},
                    }
                    db_step.finished_at = datetime.now(UTC)
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    context["last_output"] = skip_reason
                    await self._emit(
                        project_id,
                        run_id,
                        "run.step_completed",
                        agent_name=step_key,
                        data=skip_reason,
                    )
                    # Advance past remaining trade steps to journal
                    skip_count = int((config or {}).get("skip_steps_on_auto", 0))
                    idx += skip_count + 1
                    run.current_step_index = idx
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    continue

                in_warmup = closed_count < warmup_trades
                winrate_pass = winrate >= threshold

                # Warmup-window behavior is project-configurable (W22E). Resolve the mode ONLY
                # during warmup; the post-warmup winrate logic below is unchanged. Resolution
                # fails closed to pending_approval (see app.services.warmup_policy).
                warmup_mode = (
                    await resolve_warmup_mode(self.db, project_id, config) if in_warmup else None
                )
                action = decide_warmup_action(
                    in_warmup=in_warmup,
                    winrate_pass=winrate_pass,
                    warmup_mode=warmup_mode or DEFAULT_WARMUP_MODE,
                )

                if action == "auto_execute":
                    trigger = "warmup" if in_warmup else f"winrate={winrate:.1f}%>={threshold}%"
                    auto_result = await self._auto_execute_trade_proposal(project_id, run_id)
                    db_step.status = "completed"
                    db_step.output_json = {
                        "output": auto_result,
                        "meta": {
                            "winrate": winrate,
                            "threshold": threshold,
                            "closed_count": closed_count,
                            "warmup_trades": warmup_trades,
                            "auto_executed": True,
                            "trigger": trigger,
                            "warmup_mode": warmup_mode,  # set only during warmup
                        },
                    }
                    db_step.finished_at = datetime.now(UTC)
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    skip_count = int((config or {}).get("skip_steps_on_auto", 0))
                    idx += skip_count
                    context["last_output"] = auto_result
                    context["auto_trade_executed"] = True
                    await self._emit(
                        project_id,
                        run_id,
                        "run.step_completed",
                        agent_name=step_key,
                        data=f"Auto-executed ({trigger})",
                    )
                    idx += 1
                    run.current_step_index = idx
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    continue

                if action == "validation_only":
                    # Warmup proposal validated but NO order placed (project warmup_mode).
                    no_order_msg = (
                        f"WARMUP_VALIDATION_ONLY: warmup proposal validated, no order placed "
                        f"(closed={closed_count}<{warmup_trades}, winrate={winrate:.1f}%)."
                    )
                    db_step.status = "completed"
                    db_step.output_json = {
                        "output": no_order_msg,
                        "meta": {
                            "winrate": winrate,
                            "threshold": threshold,
                            "closed_count": closed_count,
                            "warmup_trades": warmup_trades,
                            "auto_executed": False,
                            "trigger": "warmup",
                            "warmup_mode": "validation_only",
                        },
                    }
                    db_step.finished_at = datetime.now(UTC)
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    context["last_output"] = no_order_msg
                    await self._emit(
                        project_id,
                        run_id,
                        "run.step_completed",
                        agent_name=step_key,
                        data=no_order_msg,
                    )
                    # Advance past remaining trade steps to journal (no order placed).
                    skip_count = int((config or {}).get("skip_steps_on_auto", 0))
                    idx += skip_count + 1
                    run.current_step_index = idx
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    continue

                if action == "pending_approval":
                    # Warmup proposal must NOT auto-execute: route to the existing approval/
                    # waiting path. resume_approved advances to the execute step on approval.
                    db_step.status = "waiting_approval"
                    db_step.output_json = {
                        "output": (
                            "WARMUP_PENDING_APPROVAL: awaiting human approval (no order placed)."
                        ),
                        "meta": {
                            "winrate": winrate,
                            "threshold": threshold,
                            "closed_count": closed_count,
                            "warmup_trades": warmup_trades,
                            "auto_executed": False,
                            "trigger": "warmup",
                            "warmup_mode": "pending_approval",
                        },
                    }
                    run.status = "waiting_approval"
                    run.current_step_index = idx
                    run.paused_at = datetime.now(UTC)
                    run.pause_reason = "warmup_pending_approval"
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    await self.db.commit()
                    await self._emit(
                        project_id,
                        run_id,
                        "run.waiting_approval",
                        agent_name=step_key,
                        data=(
                            f"Warmup pending approval (closed={closed_count}<{warmup_trades}): "
                            "no order placed"
                        ),
                    )
                    return run

                # action == "below_threshold": past warmup AND winrate < threshold.
                # Existing behavior, UNCHANGED: "skip" (NO_TRADE) or "pause" (human approval).
                if below_threshold_action == "skip":
                    skip_reason = (
                        f"NO_TRADE: winrate={winrate:.1f}% < {threshold}% "
                        f"with {closed_count} closed trades — skipping."
                    )
                    db_step.status = "completed"
                    db_step.output_json = {
                        "output": skip_reason,
                        "meta": {
                            "winrate": winrate,
                            "threshold": threshold,
                            "auto_executed": False,
                        },
                    }
                    db_step.finished_at = datetime.now(UTC)
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    context["last_output"] = skip_reason
                    await self._emit(
                        project_id,
                        run_id,
                        "run.step_completed",
                        agent_name=step_key,
                        data=skip_reason,
                    )
                    # Advance past remaining trade steps to journal
                    skip_count = int((config or {}).get("skip_steps_on_auto", 0))
                    idx += skip_count + 1
                    run.current_step_index = idx
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    continue
                else:
                    # Legacy mode: pause for human approval
                    db_step.status = "waiting_approval"
                    run.status = "waiting_approval"
                    run.current_step_index = idx
                    run.paused_at = datetime.now(UTC)
                    run.pause_reason = "approval"
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    await self.db.commit()
                    await self._emit(
                        project_id,
                        run_id,
                        "run.waiting_approval",
                        agent_name=step_key,
                        data=f"Winrate={winrate:.1f}% < {threshold}%: awaiting human approval",
                    )
                    return run

            # ── Approval gate: pause and return ──
            if step_kind == "approval":
                run.status = "waiting_approval"
                run.current_step_index = idx
                run.paused_at = datetime.now(UTC)
                run.pause_reason = "approval"
                db_step.status = "waiting_approval"
                await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                await run_repo.update_run(self.db, db_run=run, update_data={})
                await self.db.commit()
                await self.tracer.emit(
                    event_type="step.waiting_approval",
                    project_id=project_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    summary=f"Awaiting approval at {step_key}",
                    event_status="waiting_approval",
                )
                await self._emit(
                    project_id,
                    run_id,
                    "run.waiting_approval",
                    agent_name=step_key,
                    data="Awaiting human approval",
                )
                return run

            # ── Execute the step ──
            logger.info(
                "[%s] step_start step=%s kind=%s", self._htrace(run_id), step_key, step_kind
            )
            try:
                output_text, step_meta = await self._run_step(
                    project_id=project_id,
                    run_id=run_id,
                    run_step_id=db_step.id,
                    step_kind=step_kind,
                    config=config,
                    agent_key=step_def.get("agent_key") or config.get("agent_key"),
                    context=context,
                )
            except Exception as exc:
                # Recoverable LLM errors (429/quota/rate-limit/provider-down/auth) PAUSE for
                # the recovery worker to resume once retry_after elapses, rather than hard-failing
                # the whole run. Anything we can't classify is a genuine failure.
                info = classify_llm_error(exc)
                if info.error_type != "unknown_llm_error":
                    return await self._pause(run, db_step, idx, info, project_id, run_id, trace_id)
                return await self._fail(run, db_step, str(exc), project_id, run_id, trace_id)

            tokens = step_meta.get("tokens_used")
            if isinstance(tokens, int):
                total_tokens += tokens
            _out_bytes = len(output_text.encode("utf-8")) if output_text else 0
            logger.info(
                "[%s] step_done step=%s runtime=%s model=%s out_bytes=%d tokens=%s",
                self._htrace(run_id),
                step_key,
                step_meta.get("runtime", "-"),
                step_meta.get("model", "-"),
                _out_bytes,
                tokens,
            )

            # Re-run HAWK analysis steps if output is non-empty but not valid JSON.
            # Empty output is handled by Phase 6.6.A below (uses repair prompt).
            if step_kind == "prompt" and step_key in _HAWK_STEP_KEYS:
                _retry = 0
                while _retry < 2 and (
                    output_text.strip() != "" and extract_json_object(output_text) is None
                ):
                    _retry += 1
                    logger.warning(
                        "HAWK step '%s' returned invalid output — retry %d/2", step_key, _retry
                    )
                    await self._emit(
                        project_id,
                        run_id,
                        "run.step_retry",
                        agent_name=step_key,
                        data=f"{step_key}: output not JSON, retrying ({_retry}/2)",
                    )
                    try:
                        output_text, step_meta = await self._run_step(
                            project_id=project_id,
                            run_id=run_id,
                            run_step_id=db_step.id,
                            step_kind=step_kind,
                            config=config,
                            agent_key=step_def.get("agent_key") or config.get("agent_key"),
                            context=context,
                        )
                        tokens = step_meta.get("tokens_used")
                        if isinstance(tokens, int):
                            total_tokens += tokens
                    except Exception as exc:
                        logger.error("HAWK step '%s' retry %d raised: %s", step_key, _retry, exc)
                        break

            # Phase 6.6.A — HAWK empty-output retry with targeted repair prompt.
            # Must run BEFORE the outer output_text.strip() guard below, which is
            # never entered when output is empty (token ceiling / silent failure).
            if step_kind == "prompt" and step_key in _HAWK_STEP_KEYS and not output_text.strip():
                _empty_assess = assess_hawk_output_reliability(
                    output_text,
                    tokens_used=step_meta.get("tokens_used"),
                    max_tokens=step_meta.get("max_tokens"),
                )
                _empty_retry_reason = (
                    "empty_ceiling" if _empty_assess["reached_token_ceiling"] else "empty_output"
                )
                logger.warning(
                    "HAWK step '%s' returned empty output (%s) — retry once with repair prompt",
                    step_key,
                    _empty_retry_reason,
                )
                await self._emit(
                    project_id,
                    run_id,
                    "run.step_retry",
                    agent_name=step_key,
                    data=f"{step_key}: empty output ({_empty_retry_reason}), retrying once with repair prompt",
                )
                try:
                    _empty_repair_config = dict(config)
                    _empty_repair_config["prompt"] = build_hawk_repair_prompt(
                        "",
                        role=step_key,
                        market_data_summary=render_market_data_for_hawk(
                            context.get("market_data") or {}
                        ),
                    )
                    _empty_retry_output, _empty_retry_meta = await self._run_step(
                        project_id=project_id,
                        run_id=run_id,
                        run_step_id=db_step.id,
                        step_kind=step_kind,
                        config=_empty_repair_config,
                        agent_key=step_def.get("agent_key") or config.get("agent_key"),
                        context=context,
                    )
                    _empty_tokens = _empty_retry_meta.get("tokens_used")
                    if isinstance(_empty_tokens, int):
                        total_tokens += _empty_tokens
                    _empty_retry_meta["retry_count"] = 1
                    _empty_retry_meta["retry_reason"] = _empty_retry_reason
                    if _empty_retry_output.strip():
                        _p66a_initial_via = step_meta.get("market_data_injected_via")
                        output_text = _empty_retry_output
                        step_meta = _empty_retry_meta
                        step_meta["market_data_injected_via_initial"] = _p66a_initial_via
                        step_meta["retry_prompt_injected_via"] = "repair_prompt"
                    else:
                        step_meta["retry_count"] = 1
                        step_meta["retry_reason"] = _empty_retry_reason
                        step_meta["block_reason"] = "hawk_empty_output_after_retry"
                except Exception as _empty_exc:
                    logger.error(
                        "HAWK step '%s' empty-output retry raised: %s", step_key, _empty_exc
                    )
                    step_meta["retry_count"] = 1
                    step_meta["retry_reason"] = _empty_retry_reason
                    step_meta["block_reason"] = "hawk_empty_output_after_retry"

            db_step.output_json = {"output": output_text, "meta": step_meta}
            db_step.status = "completed"
            db_step.finished_at = datetime.now(UTC)
            await run_repo.update_run_step(self.db, db_step=db_step, update_data={})

            # ── Cost tracking ──────────────────────────────────────────────
            if step_kind == "prompt" and isinstance(tokens, int) and tokens > 0:
                try:
                    guard = CostGuard(self.db)
                    budget_status = await guard.record(
                        project_id=project_id,
                        run_id=run_id,
                        provider=step_meta.get("runtime", "unknown"),
                        model=step_meta.get("model", ""),
                        tokens=tokens,
                    )
                    if budget_status == "hard_stop":
                        return await self._fail(
                            run,
                            db_step,
                            "Daily cost budget exceeded — run aborted",
                            project_id,
                            run_id,
                            trace_id,
                        )
                except Exception as exc:
                    logger.warning("CostGuard.record failed: %s", exc)

            # ── Obsidian vault export ───────────────────────────────────────
            if step_kind == "prompt" and output_text:
                try:
                    agent_name = step_def.get("agent_key") or step_def.get("label") or "agent"
                    obsidian_export(
                        project_id=project_id,
                        run_id=run_id,
                        step_index=idx,
                        agent_name=str(agent_name),
                        step_kind=step_kind,
                        output_text=output_text,
                        tokens_used=tokens if isinstance(tokens, int) else None,
                    )
                except Exception as exc:
                    logger.warning("ObsidianExporter.export_step failed: %s", exc)

            context["last_output"] = output_text

            # Keep individual HAWK outputs in context so SAGE can read each one.
            if step_kind == "prompt" and step_key in _HAWK_STEP_KEYS:
                context[f"{step_key}_output"] = output_text

            if step_kind == "market_data" and output_text.strip():
                try:
                    _raw = await CryptoPersistenceService(self.db).store_raw_payload(
                        project_id=project_id,
                        run_id=run_id,
                        payload_kind="market_data",
                        agent_role="market_data",
                        step_key=step_key,
                        payload=extract_json_object(output_text) or {},
                    )
                    logger.info(
                        "[%s] raw_payload_stored id=%s kind=market_data step=%s",
                        self._htrace(run_id),
                        _raw.id,
                        step_key,
                    )
                except Exception as exc:
                    logger.warning("CryptoPersistenceService.store_raw_payload failed: %s", exc)

            # ── Crypto handoff null-validator ───────────────────────────────
            if step_kind == "prompt" and output_text.strip():
                try:
                    from app.core.json_utils import extract_json_object as _ejson

                    _parsed = _ejson(output_text)
                    # Resolve role from loaded agent if source key was replaced with UUID
                    _agent = None
                    with contextlib.suppress(Exception):
                        _agent = await self._resolve_agent(project_id, step_def.get("agent_key"))
                    role_name = (_agent.role if _agent else None) or step_key
                    _ctx_for_validator = {
                        "_market_price": (context.get("market_data") or {}).get("price"),
                        "majority_direction": context.get("majority_direction"),
                        "market_type": context.get("market_type"),
                        "vote_tally": context.get("vote_tally"),
                    }
                    _repair_metadata: dict = {}
                    _retry_attempted = False
                    _model_used = step_meta.get("model", "-")

                    # ── HAWK invalid / truncated JSON: one bounded repair retry ──
                    # When _parsed is None the model output is unparseable or
                    # truncated (e.g. a bare "{" emitted after hitting num_predict).
                    # The deterministic repair + schema-retry path below only handles
                    # already-parseable JSON, so cover the None case here with exactly
                    # ONE strict-JSON repair retry. Never synthesize vote or
                    # invalidation_level — the model must re-emit them. If the retry
                    # still does not parse, fall through unchanged and let the gate
                    # block fail-closed.
                    if role_name in _HAWK_STEP_KEYS and _parsed is None and not _retry_attempted:
                        _retry_attempted = True
                        _assess = assess_hawk_output_reliability(
                            output_text,
                            tokens_used=step_meta.get("tokens_used"),
                            max_tokens=step_meta.get("max_tokens"),
                        )
                        _retry_reason = (
                            "truncated_json"
                            if _assess["output_truncated_detected"]
                            else "invalid_json"
                        )
                        logger.warning(
                            "HAWK step '%s' produced unparseable JSON (%s) — retry once "
                            "with strict-JSON repair prompt",
                            step_key,
                            _retry_reason,
                        )
                        await self._emit(
                            project_id,
                            run_id,
                            "run.step_retry",
                            agent_name=step_key,
                            data=f"{step_key}: invalid/truncated JSON ({_retry_reason}), "
                            "retrying once with strict-JSON repair prompt",
                        )
                        try:
                            _repair_config = dict(config)
                            _repair_config["prompt"] = build_hawk_repair_prompt(
                                output_text,
                                role=role_name,
                                market_data_summary=render_market_data_for_hawk(
                                    context.get("market_data") or {}
                                ),
                            )
                            _retry_output, _retry_meta = await self._run_step(
                                project_id=project_id,
                                run_id=run_id,
                                run_step_id=db_step.id,
                                step_kind=step_kind,
                                config=_repair_config,
                                agent_key=step_def.get("agent_key") or config.get("agent_key"),
                                context=context,
                            )
                            _retry_meta["retry_count"] = 1
                            _retry_meta["retry_reason"] = _retry_reason
                            _retry_parsed = _ejson(_retry_output)
                            _tokens = _retry_meta.get("tokens_used")
                            if isinstance(_tokens, int):
                                total_tokens += _tokens
                            if isinstance(_retry_parsed, dict):
                                # Recovered. Persist the retried payload so the
                                # downstream gate (which re-reads db_step.output_json)
                                # evaluates the recovered output, not the truncated text.
                                _p2_initial_via = step_meta.get("market_data_injected_via")
                                output_text = _retry_output
                                _parsed = _retry_parsed
                                step_meta = _retry_meta
                                step_meta["market_data_injected_via_initial"] = _p2_initial_via
                                step_meta["retry_prompt_injected_via"] = "repair_prompt"
                                _model_used = _retry_meta.get("model", _model_used)
                                context["last_output"] = output_text
                                context[f"{step_key}_output"] = output_text
                                db_step.output_json = {"output": output_text, "meta": step_meta}
                                await run_repo.update_run_step(
                                    self.db, db_step=db_step, update_data={}
                                )
                            else:
                                # Still unparseable → keep retry meta + block_reason
                                # for observability; gate blocks fail-closed below.
                                step_meta["retry_count"] = 1
                                step_meta["retry_reason"] = _retry_reason
                                step_meta["block_reason"] = "hawk_unparseable_json_after_retry"
                                db_step.output_json = {"output": output_text, "meta": step_meta}
                                await run_repo.update_run_step(
                                    self.db, db_step=db_step, update_data={}
                                )
                        except Exception as _retry_exc:
                            logger.error(
                                "HAWK step '%s' invalid-JSON repair retry raised: %s",
                                step_key,
                                _retry_exc,
                            )
                            step_meta["retry_count"] = 1
                            step_meta["retry_reason"] = _retry_reason
                            step_meta["block_reason"] = "hawk_unparseable_json_after_retry"

                    # ── HAWK-specific deterministic repair + one schema retry ──
                    if role_name in _HAWK_STEP_KEYS and isinstance(_parsed, dict):
                        _parsed, _repair_metadata = repair_hawk_output(output_text, role=role_name)
                        if isinstance(_parsed, dict):
                            output_text = json.dumps(_parsed, ensure_ascii=False)

                    if isinstance(_parsed, dict):
                        # ── Phase 6.14.O: deterministic approval_status normalization ──
                        # The compile_proposal (trade_proposal) agent often omits
                        # approval_status even though the prompt instructs PENDING_APPROVAL;
                        # the null-validator then reads None and hard-blocks. Default a
                        # missing/None value to PENDING_APPROVAL here, and fail closed if the
                        # agent tries to self-elevate to APPROVED/EXECUTED at compile time.
                        if role_name == "trade_proposal":
                            _parsed, _as_meta, _as_block = (
                                normalize_compile_proposal_approval_status(_parsed)
                            )
                            for _ak, _av in _as_meta.items():
                                step_meta[_ak] = _av
                            if _as_meta or _as_block:
                                output_text = json.dumps(_parsed, ensure_ascii=False)
                                context["last_output"] = output_text
                                db_step.output_json = {"output": output_text, "meta": step_meta}
                                await run_repo.update_run_step(
                                    self.db, db_step=db_step, update_data={}
                                )
                            if _as_block:
                                logger.warning(
                                    "Crypto handoff validator CRITICAL failure at '%s' "
                                    "(role=%s): %s",
                                    step_key,
                                    role_name,
                                    _as_block,
                                )
                                await self._emit(
                                    project_id,
                                    run_id,
                                    "run.handoff_warning",
                                    agent_name=step_key,
                                    data=f"Handoff validation CRITICAL: {_as_block}",
                                )
                                return await self._block(
                                    run,
                                    db_step,
                                    f"Handoff validation failed at '{step_key}' "
                                    f"({role_name}): {_as_block}",
                                    project_id,
                                    run_id,
                                    trace_id,
                                    pause_reason="handoff_validation_failed",
                                )

                        _valid, _violations = validate_step_output(
                            role_name, _parsed, _ctx_for_validator
                        )

                        # One retry for schema-only HAWK failures (bad vote/confidence format).
                        if role_name in _HAWK_STEP_KEYS and not _valid and not _retry_attempted:
                            _critical = [v for v in _violations if v.critical]
                            _schema_only = _critical and all(
                                v.field in {"vote", "confidence"} for v in _critical
                            )
                            if _schema_only:
                                _retry_attempted = True
                                logger.warning(
                                    "HAWK step '%s' schema repair failed — retry once with repair prompt",
                                    step_key,
                                )
                                await self._emit(
                                    project_id,
                                    run_id,
                                    "run.step_retry",
                                    agent_name=step_key,
                                    data=f"{step_key}: schema repair failed, retrying with repair prompt",
                                )
                                try:
                                    _repair_config = dict(config)
                                    _repair_config["prompt"] = build_hawk_repair_prompt(
                                        output_text,
                                        role=role_name,
                                        market_data_summary=render_market_data_for_hawk(
                                            context.get("market_data") or {}
                                        ),
                                    )
                                    _retry_output, _retry_meta = await self._run_step(
                                        project_id=project_id,
                                        run_id=run_id,
                                        run_step_id=db_step.id,
                                        step_kind=step_kind,
                                        config=_repair_config,
                                        agent_key=step_def.get("agent_key")
                                        or config.get("agent_key"),
                                        context=context,
                                    )
                                    _retry_parsed = _ejson(_retry_output)
                                    if isinstance(_retry_parsed, dict):
                                        _parsed, _repair_meta2 = repair_hawk_output(
                                            _retry_output, role=role_name
                                        )
                                        _repair_metadata["retry_repair"] = _repair_meta2
                                        _repair_metadata["retry_repaired"] = _repair_meta2.get(
                                            "repaired", False
                                        )
                                        output_text = json.dumps(_parsed, ensure_ascii=False)
                                        _schema_initial_via = step_meta.get(
                                            "market_data_injected_via"
                                        )
                                        step_meta = _retry_meta
                                        step_meta["market_data_injected_via_initial"] = (
                                            _schema_initial_via
                                        )
                                        step_meta["retry_prompt_injected_via"] = "repair_prompt"
                                        _tokens = _retry_meta.get("tokens_used")
                                        if isinstance(_tokens, int):
                                            total_tokens += _tokens
                                        _model_used = _retry_meta.get("model", _model_used)
                                        _valid, _violations = validate_step_output(
                                            role_name, _parsed, _ctx_for_validator
                                        )
                                except Exception as _retry_exc:
                                    logger.error(
                                        "HAWK step '%s' repair retry raised: %s",
                                        step_key,
                                        _retry_exc,
                                    )

                        if _violations:
                            violation_msgs = "; ".join(str(v) for v in _violations)
                            if not _valid:
                                logger.warning(
                                    "Crypto handoff validator CRITICAL failure at '%s' (role=%s): %s",
                                    step_key,
                                    role_name,
                                    violation_msgs,
                                )
                                await self._emit(
                                    project_id,
                                    run_id,
                                    "run.handoff_warning",
                                    agent_name=step_key,
                                    data=f"Handoff validation CRITICAL: {violation_msgs}",
                                )
                                # Update output_text with repaired payload (if auto-repair was applied)
                                try:
                                    output_text = json.dumps(_parsed, ensure_ascii=False)
                                    context["last_output"] = output_text
                                    if step_key in _HAWK_STEP_KEYS:
                                        context[f"{step_key}_output"] = output_text
                                    db_step.output_json = {
                                        "output": output_text,
                                        "meta": {
                                            **step_meta,
                                            "hawk_repair": _repair_metadata,
                                        },
                                    }
                                    await run_repo.update_run_step(
                                        self.db, db_step=db_step, update_data={}
                                    )
                                except Exception:
                                    pass
                                # Structured block details for HAWK; keep proposal hints for trade_proposal.
                                _hint = ""
                                if role_name in _HAWK_STEP_KEYS:
                                    _hint = " | " + format_hawk_block_details(
                                        step_key=step_key,
                                        role=role_name,
                                        model=_model_used,
                                        violations=_violations,
                                        raw_preview=output_text,
                                        repaired=_repair_metadata.get("repaired", False),
                                        retry_attempted=_retry_attempted,
                                    )
                                elif any(
                                    kw in violation_msgs
                                    for kw in (
                                        "direction_majority_mismatch",
                                        "majority_direction_unavailable",
                                        "spot_short_unsupported",
                                    )
                                ):
                                    _md = context.get("majority_direction") or "unknown"
                                    _tally = context.get("vote_tally") or {}
                                    _lvls = context.get("hawk_invalidation_levels") or ""
                                    _prop_dir = _parsed.get("direction", "unknown")
                                    from app.services.crypto_handoff_validator import (
                                        _MAJORITY_TO_DIRECTION,
                                    )

                                    _exp_dir = _MAJORITY_TO_DIRECTION.get(
                                        str(_md).upper(), "BLOCKED"
                                    )
                                    _hint = (
                                        f" | Remediation: proposal_direction={_prop_dir}, "
                                        f"majority_direction={_md}, expected_direction={_exp_dir}, "
                                        f"vote_tally={_tally}"
                                    )
                                    if _lvls:
                                        _hint += f", hawk_invalidation_levels={_lvls}"
                                elif "stop_loss" in violation_msgs:
                                    _levels_raw = context.get("hawk_invalidation_levels")
                                    if _levels_raw:
                                        _side = (
                                            "above entry"
                                            if "short_stop_loss" in violation_msgs
                                            else "below entry"
                                            if "long_stop_loss" in violation_msgs
                                            else "the correct side of entry"
                                        )
                                        _hint = (
                                            f" | Remediation: select stop_loss {_side} from/justified "
                                            f"against HAWK invalidation levels {_levels_raw}"
                                        )
                                return await self._block(
                                    run,
                                    db_step,
                                    f"Handoff validation failed at '{step_key}' ({role_name}): "
                                    f"{violation_msgs}{_hint}",
                                    project_id,
                                    run_id,
                                    trace_id,
                                    pause_reason="handoff_validation_failed",
                                )
                            else:
                                # Non-critical violations (warnings + auto-repairs)
                                logger.info(
                                    "Crypto handoff auto-repaired '%s': %s",
                                    step_key,
                                    violation_msgs,
                                )
                                try:
                                    output_text = json.dumps(_parsed, ensure_ascii=False)
                                    context["last_output"] = output_text
                                    if step_key in _HAWK_STEP_KEYS:
                                        context[f"{step_key}_output"] = output_text
                                    db_step.output_json = {
                                        "output": output_text,
                                        "meta": {
                                            **step_meta,
                                            "hawk_repair": _repair_metadata,
                                        },
                                    }
                                    await run_repo.update_run_step(
                                        self.db, db_step=db_step, update_data={}
                                    )
                                except Exception:
                                    pass
                except Exception as _exc:
                    logger.debug("Crypto handoff validator skipped for '%s': %s", step_key, _exc)

            # ── Normalize compile_proposal output, then force market_type ──
            # Normalization runs before the handoff validator so fenced JSON is repaired
            # and truncated output fails closed with a specific reason rather than a
            # generic "not a valid JSON object" message.
            # market_type is always overridden from runtime context — the LLM must never
            # control it (e.g. "spot" when MARKET_TYPE=futures must be corrected here).
            if step_key == "compile_proposal" and step_kind == "prompt" and output_text.strip():
                try:
                    from app.core.json_utils import normalize_llm_json_output as _nljo

                    _norm_parsed, _norm_meta = _nljo(output_text)
                    # Merge normalization metadata into step_meta for audit trail.
                    for _nk, _nv in _norm_meta.items():
                        if _nv is not None:
                            step_meta[_nk] = _nv

                    if _norm_parsed is None:
                        # Fail closed with the specific parse error reason.
                        _parse_err = (
                            _norm_meta.get("parse_error") or "compile_proposal_invalid_json"
                        )
                        logger.warning(
                            "[%s] compile_proposal output unparseable (%s) — blocking run "
                            "(had_fence=%s truncated=%s)",
                            self._htrace(run_id) if hasattr(self, "_htrace") else "?",
                            _parse_err,
                            _norm_meta.get("had_markdown_fence"),
                            _norm_meta.get("truncated_detected"),
                        )
                        db_step.output_json = {"output": output_text, "meta": step_meta}
                        await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                        return await self._block(
                            run,
                            db_step,
                            _parse_err,
                            project_id,
                            run_id,
                            trace_id,
                            pause_reason="handoff_contract_failed",
                        )

                    # Override market_type with the deterministic runtime value.
                    _norm_parsed["market_type"] = context.get("market_type", "futures")
                    output_text = json.dumps(_norm_parsed, ensure_ascii=False)
                    context["last_output"] = output_text
                    db_step.output_json = {"output": output_text, "meta": step_meta}
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    logger.info(
                        "[%s] compile_proposal: market_type=%s had_fence=%s repaired=%s",
                        self._htrace(run_id) if hasattr(self, "_htrace") else "?",
                        _norm_parsed["market_type"],
                        _norm_meta.get("had_markdown_fence"),
                        _norm_meta.get("repaired_json_wrapper"),
                    )
                except Exception as _mt_exc:
                    logger.warning("compile_proposal normalization failed: %s", _mt_exc)

            next_step_key = None
            if idx + 1 < len(steps):
                next_step_key = str(steps[idx + 1].get("key") or f"step_{idx + 2}")

            try:
                handoff_failure = self._evaluate_boundary_handoff(
                    step_key=step_key,
                    next_step_key=next_step_key,
                    output_text=output_text,
                )
                if handoff_failure:
                    logger.warning(handoff_failure)
                    await self._emit(
                        project_id,
                        run_id,
                        "run.handoff_warning",
                        agent_name=step_key,
                        data=handoff_failure,
                    )
                    return await self._block(
                        run,
                        db_step,
                        handoff_failure,
                        project_id,
                        run_id,
                        trace_id,
                        pause_reason="handoff_contract_failed",
                    )
                elif next_step_key:
                    logger.info(
                        "[%s] handoff_ok %s→%s", self._htrace(run_id), step_key, next_step_key
                    )
            except Exception as exc:
                logger.warning("Handoff contract enforcement failed at '%s': %s", step_key, exc)

            # ── Inter-step pacing (anti-rate-limit) ─────────────────────────
            if step_kind == "prompt":
                try:
                    from app.core.config import settings as _settings

                    _delay = _settings.PIPELINE_STEP_DELAY_SECONDS
                    if _delay > 0:
                        await asyncio.sleep(_delay)
                except Exception:
                    pass

            # ── Conditional skip ──
            if step_kind == "conditional" and output_text == "false":
                skip = int(config.get("skip_steps_on_false", 0))
                if skip > 0:
                    idx += skip  # extra skip; the loop will +1 below
                    logger.info("Conditional '%s' = false, skipping %d steps", step_key, skip)

            # ── Loop jump-back ──
            if step_kind == "loop":
                loop_key = f"_loop_{step_key}"
                max_iter = int(config.get("max_iterations", 3))
                current_iter = int(context.get(loop_key, 0))

                if current_iter < max_iter:
                    context[loop_key] = current_iter + 1
                    loop_start_key = config.get("loop_start_key")
                    if loop_start_key:
                        for back_idx, s in enumerate(steps):
                            if s.get("key") == loop_start_key:
                                run.current_step_index = back_idx
                                await run_repo.update_run(self.db, db_run=run, update_data={})
                                idx = back_idx
                                break
                    await self.tracer.emit(
                        event_type="step.completed",
                        project_id=project_id,
                        run_id=run_id,
                        trace_id=trace_id,
                        summary=f"{step_key} completed",
                        event_status="completed",
                        payload={"tokens_used": None},
                    )
                    await self._emit(
                        project_id,
                        run_id,
                        "run.step_output",
                        agent_name=step_key,
                        data=output_text[:4000],
                    )
                    await self._emit(
                        project_id,
                        run_id,
                        "run.step_completed",
                        agent_name=step_key,
                        data=f"{step_kind} completed",
                    )
                    # Skip normal idx increment — we already repositioned idx.
                    continue
                else:
                    # Loop exhausted — reset counter and fall through to normal idx += 1.
                    context.pop(loop_key, None)

            await self.tracer.emit(
                event_type="step.completed",
                project_id=project_id,
                run_id=run_id,
                trace_id=trace_id,
                summary=f"{step_key} completed",
                event_status="completed",
                payload={"tokens_used": tokens},
            )
            await self._emit(
                project_id, run_id, "run.step_output", agent_name=step_key, data=output_text[:4000]
            )
            await self._emit(
                project_id,
                run_id,
                "run.step_completed",
                agent_name=step_key,
                data=f"{step_kind} completed",
            )

            _is_hawk_gate = step_kind == "hawk_vote" or step_meta.get("runtime") == "hawk_vote"
            if _is_hawk_gate and not bool(step_meta.get("gate_passed")):
                gate_message = str(
                    step_meta.get("gate_reason")
                    or "HAWK majority gate blocked the run before SAGE review"
                )
                invalid_steps = step_meta.get("invalid_steps") or []

                if invalid_steps:
                    # True runtime failure: step didn't complete or output was unparseable.
                    return await self._fail(
                        run,
                        db_step,
                        gate_message,
                        project_id,
                        run_id,
                        trace_id,
                    )
                # No-majority block — include vote details and any dq_flags as context.
                _gate_votes: dict = step_meta.get("votes") or {}
                _gate_tally: dict = step_meta.get("vote_tally") or {}
                _gate_dq: dict = step_meta.get("dq_flags") or {}
                if _gate_votes:
                    vote_lines = " | ".join(f"{k}: {v}" for k, v in _gate_votes.items())
                    tally_line = f"BULLISH {_gate_tally.get('BULLISH', 0)} / BEARISH {_gate_tally.get('BEARISH', 0)} / NEUTRAL {_gate_tally.get('NEUTRAL', 0)}"
                    gate_message = f"{gate_message}\n{vote_lines}\nTally: {tally_line}"
                if _gate_dq:
                    dq_summary = "; ".join(f"{s}={v}" for s, v in _gate_dq.items())
                    gate_message = f"{gate_message}\ndq_flags: {dq_summary}"
                return await self._block(
                    run,
                    db_step,
                    gate_message,
                    project_id,
                    run_id,
                    trace_id,
                    pause_reason="hawk_vote_no_majority",
                )

            # Build $hawk_vote_result and check invalidation_level for directional votes.
            # The missing_invalidation_levels list is computed inside _run_hawk_vote (where
            # DB-loaded payloads are available) and surfaced through step_meta.
            if _is_hawk_gate and bool(step_meta.get("gate_passed")):
                _inv_missing: list[str] = step_meta.get("missing_invalidation_levels") or []
                _inv_levels: dict = step_meta.get("invalidation_levels") or {}
                if _inv_missing:
                    logger.warning(
                        "[%s] hawk_invalidation_level_missing steps=%s",
                        self._htrace(run_id),
                        _inv_missing,
                    )
                    return await self._block(
                        run,
                        db_step,
                        f"HAWK directional votes missing invalidation_level: {_inv_missing}",
                        project_id,
                        run_id,
                        trace_id,
                        pause_reason="hawk_missing_invalidation_level",
                    )
                context["hawk_invalidation_levels"] = json.dumps(_inv_levels, ensure_ascii=False)
                # Publish majority_direction and vote_tally as top-level context keys so
                # validate_trade_proposal_output can enforce direction alignment without
                # re-parsing the hawk_vote_result JSON blob.
                context["majority_direction"] = step_meta.get("majority_direction", "")
                context["vote_tally"] = step_meta.get("vote_tally") or {}
                hawk_individual = {
                    k: context.get(f"{k}_output", "")
                    for k in ("hawk_trend", "hawk_structure", "hawk_counter")
                }
                context["hawk_vote_result"] = json.dumps(
                    {"vote_gate": output_text, "hawk_outputs": hawk_individual},
                    ensure_ascii=False,
                )
                if validation_only["enabled"]:
                    stop_summary = {
                        "validation_only": True,
                        "mode_source": validation_only["source"],
                        "stopped_after": "hawk_vote_gate",
                        "stopped_before": self._next_step_key(steps, idx),
                        "hawk_vote_gate_passed": True,
                        "majority_direction": step_meta.get("majority_direction", ""),
                        "vote_tally": step_meta.get("vote_tally") or {},
                        "no_order_placed": True,
                    }
                    db_step.output_json = {
                        "output": output_text,
                        "meta": {
                            **step_meta,
                            "validation_only": True,
                            "stopped_after": "hawk_vote_gate",
                            "stopped_before": stop_summary["stopped_before"],
                            "no_order_placed": True,
                        },
                    }
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    run.status = "completed"
                    run.output_text = json.dumps(stop_summary, ensure_ascii=False)
                    run.finished_at = datetime.now(UTC)
                    run.current_step_index = idx + 1
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    await self.db.commit()

                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    try:
                        await self.metrics.complete_run(
                            run_id, step_count=idx + 1, duration_ms=duration_ms
                        )
                    except Exception as exc:
                        logger.warning("MetricsTracker.complete_run failed: %s", exc)

                    await run_repo.upsert_run_metric(
                        self.db,
                        run_id=run_id,
                        project_id=project_id,
                        step_count=idx + 1,
                        duration_ms=duration_ms,
                        total_tokens=total_tokens,
                    )
                    await self.tracer.emit(
                        event_type="run.completed",
                        project_id=project_id,
                        run_id=run_id,
                        trace_id=trace_id,
                        summary="Validation-only run completed after HAWK vote gate",
                        event_status="completed",
                        payload=stop_summary,
                    )
                    await self._emit(
                        project_id,
                        run_id,
                        "run.completed",
                        agent_name="orchestrator",
                        data="Validation-only run completed after HAWK vote gate; no order placed",
                    )
                    return run

            # ── SAGE veto gate ─────────────────────────────────────────────────────
            # If any prompt step outputs sage_decision=VETOED, stop the pipeline now
            # instead of letting compile_proposal and execution steps run on bad data.
            if step_kind in ("prompt", "delegate"):
                is_vetoed, veto_reason = _extract_sage_veto(output_text)
                if is_vetoed:
                    veto_message = f"SAGE vetoed the trade: {veto_reason}"
                    return await self._block(
                        run,
                        db_step,
                        veto_message,
                        project_id,
                        run_id,
                        trace_id,
                        pause_reason="sage_veto",
                    )

            idx += 1
            run.current_step_index = idx
            await run_repo.update_run(self.db, db_run=run, update_data={})

        # ── Finished ──
        run.status = "completed"
        run.output_text = context.get("last_output") or ""
        run.finished_at = datetime.now(UTC)
        run.current_step_index = len(steps)
        await run_repo.update_run(self.db, db_run=run, update_data={})
        await self.db.commit()

        duration_ms = int((time.monotonic() - start_time) * 1000)

        try:
            await self.metrics.complete_run(run_id, step_count=len(steps), duration_ms=duration_ms)
        except Exception as exc:
            logger.warning("MetricsTracker.complete_run failed: %s", exc)

        await run_repo.upsert_run_metric(
            self.db,
            run_id=run_id,
            project_id=project_id,
            step_count=len(steps),
            duration_ms=duration_ms,
            total_tokens=total_tokens,
        )

        await self.tracer.emit(
            event_type="run.completed",
            project_id=project_id,
            run_id=run_id,
            trace_id=trace_id,
            summary="Run completed",
            event_status="completed",
            payload={
                "step_count": len(steps),
                "duration_ms": duration_ms,
                "total_tokens": total_tokens,
            },
        )
        await self._emit(
            project_id, run_id, "run.completed", agent_name="orchestrator", data="Run completed"
        )

        # ── Post-trade learning loop ──
        # Close detection is EXCHANGE-DRIVEN when an exchange-backed snapshot is present:
        #   1a. A Position-Monitor run produces context["monitor_snapshot"] from real exchange
        #       state. In demo/testnet/live, that snapshot is the SOLE source of truth — learning
        #       triggers only for exchange-confirmed closes. The fragile LLM-text close path is
        #       NOT consulted here (it could fabricate a close the exchange contradicts).
        #   1b. Otherwise (pure paper mode, or non-monitor runs like the trade pipeline that have
        #       no snapshot) fall back to the legacy LLM-text close path + P&L-regex lesson.
        # Best-effort: a learning failure must never fail a trade run.
        try:
            from app.services.position_lifecycle import PositionLifecycleService
            from app.services.trade_learning_service import TradeLearningService

            last_out = context.get("last_output", "")
            snapshot = context.get("monitor_snapshot")
            exchange_authoritative = (
                bool(snapshot) and resolve_trading_mode().exchange_mode != "paper"
            )

            if exchange_authoritative:
                closed_trades = await PositionLifecycleService(self.db).finalize_from_snapshot(
                    project_id=project_id, run_id=run_id, snapshot=snapshot
                )
                if closed_trades:
                    await self.db.commit()
                    for closed_trade in closed_trades:
                        await TradeLearningService(self.db).reflect_and_record(
                            project_id=project_id, closed_trade=closed_trade
                        )
                await self.db.commit()
            else:
                closed_trade = await PositionLifecycleService(self.db).finalize_from_monitor_output(
                    project_id=project_id, run_id=run_id, monitor_output=last_out
                )
                if closed_trade is not None:
                    await self.db.commit()
                    await TradeLearningService(self.db).reflect_and_record(
                        project_id=project_id, closed_trade=closed_trade
                    )
                else:
                    pnl = _extract_pnl_pct(last_out)
                    if pnl is not None:
                        await TradeLearningService(self.db).trigger_post_trade_learning(
                            project_id=project_id, run_id=run_id, pnl_pct=pnl
                        )
                await self.db.commit()
        except Exception as exc:
            logger.warning("Post-trade learning failed: %s", exc)

        return run

    async def resume_approved(self, run_id: UUID, project_id: UUID) -> Run:
        """Approve a waiting run: skip the approval step and continue."""
        run = await self._load_run(run_id, project_id)
        if run.status != "waiting_approval":
            raise NotFoundError(
                message="Run is not awaiting approval",
                details={"run_id": str(run_id), "status": run.status},
            )
        # Capture the warmup-pause flag BEFORE pause_reason is cleared below. Only a run paused by
        # the warmup gate (W28E) needs its proposal promoted here — the legacy/manual approval
        # paths approve the proposal via the separate trading.py approve endpoint.
        was_warmup_pending = run.pause_reason == "warmup_pending_approval"
        # Mark the approval step completed, then advance past it.
        steps = await self._load_steps(run)
        idx = run.current_step_index or 0
        if idx < len(steps):
            step_def = steps[idx]
            db_step = await self._get_or_create_step(
                run, str(step_def.get("key") or f"step_{idx + 1}"), "approval", step_def
            )
            db_step.status = "completed"
            db_step.output_json = {"output": "approved"}
            db_step.finished_at = datetime.now(UTC)
            await run_repo.update_run_step(self.db, db_step=db_step, update_data={})

        run.current_step_index = idx + 1
        run.status = "running"
        run.paused_at = None
        run.pause_reason = ""
        await run_repo.update_run(self.db, db_run=run, update_data={})

        if was_warmup_pending:
            promoted, reason = await self._promote_warmup_proposal(project_id, run_id)
            logger.info(
                "[%s] warmup_resume proposal promotion: promoted=%s reason=%s",
                self._htrace(run_id),
                promoted,
                reason,
            )

        try:
            await self.metrics.record_review_cycle(run_id)
        except Exception as exc:
            logger.warning("MetricsTracker.record_review_cycle failed: %s", exc)

        return await self.execute(run_id, project_id)

    # Proposal statuses a warmup_pending_approval resume may promote to APPROVED. Anything else
    # (EXECUTED / REJECTED / EXPIRED / NEEDS_ATTENTION / DRAFT) is non-promotable and fails closed.
    _APPROVABLE_PROPOSAL_STATUSES = frozenset({"PENDING_APPROVAL", "BLOCKED_KILL_SWITCH"})

    async def _promote_warmup_proposal(self, project_id: UUID, run_id: UUID) -> tuple[bool, str]:
        """Promote this run's trade proposal to APPROVED for a warmup_pending_approval resume.

        Fail-closed persist-then-promote (W28E). A warmup-paused run has at most one proposal
        persisted at compile time — ``PENDING_APPROVAL`` if the kill switch passed, or
        ``BLOCKED_KILL_SWITCH`` if it did not. On an explicit human approval/resume this may
        promote that proposal to ``APPROVED`` — but ONLY after re-validating it through
        ``prepare_execution_plan``, which re-runs the kill switch (so a still-blocked proposal
        with no valid risk_ack can never be approved) plus expiry, directional-risk and
        duplicate-execution checks. This never creates a proposal, never bypasses the kill switch,
        and leaves ``execute_trade``'s ``status == "APPROVED"`` requirement untouched.

        Returns ``(promoted, reason)``. When it returns ``False`` no order can be placed:
        ``_run_exchange_execute`` finds no APPROVED proposal and skips fail-closed.
        """
        from sqlalchemy import select as _select

        from app.db.models.crypto_trading import TradeProposal

        result = await self.db.execute(
            _select(TradeProposal)
            .where(
                TradeProposal.project_id == project_id,
                TradeProposal.run_id == run_id,
            )
            .order_by(TradeProposal.created_at.desc())
            .limit(1)
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            return False, "no proposal persisted for this run"
        if proposal.status == "APPROVED":
            return True, "proposal already APPROVED"
        if proposal.status not in self._APPROVABLE_PROPOSAL_STATUSES:
            return False, f"proposal status {proposal.status} is not approvable"

        # Re-validate before approving: re-runs the kill switch and the full execution preflight.
        # require_status="" skips only the status gate (the proposal is not APPROVED yet); every
        # other safety check still runs. A failure leaves the proposal non-APPROVED → no order.
        try:
            await prepare_execution_plan(
                db=self.db,
                project_id=project_id,
                proposal=proposal,
                require_status="",
            )
        except ExecutionPreflightError as exc:
            proposal.rejection_reason = f"WARMUP_PROMOTE_BLOCKED: {exc}"
            await self.db.flush()
            return False, f"execution preflight failed: {exc}"

        proposal.status = "APPROVED"
        proposal.approved_at = datetime.now(UTC)
        await self.db.flush()
        return True, "promoted to APPROVED"

    async def resume_from_blocked(self, run_id: UUID, project_id: UUID) -> Run:
        """Override a HAWK vote gate block and resume pipeline from the next step."""
        run = await self._load_run(run_id, project_id)
        if run.status != "blocked":
            raise NotFoundError(
                message="Run is not blocked",
                details={"run_id": str(run_id), "status": run.status},
            )
        idx = (run.current_step_index or 0) + 1
        run.current_step_index = idx
        run.status = "running"
        run.error_text = ""
        run.output_text = ""
        run.finished_at = None
        run.pause_reason = ""
        await run_repo.update_run(self.db, db_run=run, update_data={})
        return await self.execute(run_id, project_id)

    async def resume_rejected(self, run_id: UUID, project_id: UUID) -> Run:
        """Reject a waiting run: cancel and finish."""
        run = await self._load_run(run_id, project_id)
        trace_id = self._trace_id(run)
        steps = await self._load_steps(run)
        idx = run.current_step_index or 0
        if idx < len(steps):
            step_def = steps[idx]
            db_step = await self._get_or_create_step(
                run, str(step_def.get("key") or f"step_{idx + 1}"), "approval", step_def
            )
            db_step.status = "cancelled"
            db_step.output_json = {"output": "rejected"}
            db_step.finished_at = datetime.now(UTC)
            await run_repo.update_run_step(self.db, db_step=db_step, update_data={})

        run.status = "cancelled"
        run.finished_at = datetime.now(UTC)
        run.paused_at = None
        run.pause_reason = "rejected"
        await run_repo.update_run(self.db, db_run=run, update_data={})

        await self.tracer.emit(
            event_type="run.cancelled",
            project_id=project_id,
            run_id=run_id,
            trace_id=trace_id,
            summary="Run rejected by approver",
            event_status="cancelled",
        )
        await self._emit(
            project_id, run_id, "run.cancelled", agent_name="orchestrator", data="Run rejected"
        )
        return run

    # ── Step handlers ─────────────────────────────────────────────────────────

    async def _run_step(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        run_step_id: UUID | None,
        step_kind: str,
        config: dict,
        agent_key: object,
        context: dict,
    ) -> tuple[str, dict]:
        if step_kind in ("prompt", "delegate"):
            return await self._run_prompt(
                project_id,
                run_id,
                run_step_id,
                config,
                agent_key,
                context,
            )
        if step_kind == "kb_search":
            return await self._run_kb_search(project_id, config, context)
        if step_kind == "write_note":
            return await self._run_write_note(project_id, config, context)
        if step_kind == "http_request":
            return await self._run_http_request(config, context)
        if step_kind == "conditional":
            if config.get("condition_type") == "hawk_vote":
                return await self._run_hawk_vote(run_id, config, context)
            return await self._run_conditional(config, context)
        if step_kind == "loop":
            # Loop control is handled in execute() — just return iteration info.
            iter_count = context.get(f"_loop_{config.get('step_key', 'loop')}", 0)
            return (f"loop_iteration_{iter_count}", {})
        if step_kind == "hawk_vote":
            return await self._run_hawk_vote(run_id, config, context)
        if step_kind == "market_data":
            return await self._run_market_data(config, context)
        if step_kind == "position_monitor":
            return await self._run_position_monitor(project_id, context)
        if step_kind == "coin_screener":
            return await self._run_coin_screener(project_id, config, context)
        if step_kind in ("auto_trade_gate", "winrate_trade_gate"):
            # Handled in execute() before this call — should not reach here.
            return ("GATE_NOOP", {"runtime": "noop", "kind": step_kind})
        if step_kind == "sub_workflow":
            return await self._run_sub_workflow(project_id, config, context)
        if step_kind == "exchange_execute":
            return await self._run_exchange_execute(project_id, run_id)
        # Unknown kind → pass the last output through unchanged.
        return context.get("last_output", ""), {"runtime": "noop", "kind": step_kind}

    async def _run_prompt(
        self,
        project_id: UUID,
        run_id: UUID,
        run_step_id: UUID | None,
        config: dict,
        agent_key: object,
        context: dict,
    ) -> tuple[str, dict]:
        agent = await self._resolve_agent(project_id, agent_key)
        template = (
            config.get("prompt")
            or config.get("prompt_template")
            or config.get("text")
            or config.get("label")
            or "$last_output"
        )
        prompt = self._substitute(str(template), context)
        if not prompt.strip():
            prompt = context.get("last_output") or "Continue."

        system_prompt = agent.system_prompt or f"You are {agent.name}, a {agent.role}."
        system_prompt = self._substitute(system_prompt, context)
        compaction_service = ContextCompactionService(self.db)
        context_items = await self._workflow_context_items(run_id)
        memory_block, compaction_record = await compaction_service.build_run_memory(
            project_id=project_id,
            run_id=run_id,
            run_step_id=run_step_id,
            agent=agent,
            items=context_items,
        )
        if memory_block:
            system_prompt = f"{system_prompt}\n\n{memory_block}"

        # Apply active skill fragment (may route to canary version for A/B testing)
        skill_ids: list = getattr(agent, "skill_ids", None) or []
        active_skill_id: UUID | None = None
        if skill_ids:
            from uuid import UUID as _UUID

            from app.services.skill_version import SkillVersionService

            svc = SkillVersionService(self.db)
            try:
                sid = _UUID(str(skill_ids[0]))
                active_skill_id = sid
                system_prompt = await svc.get_active_fragment(sid, system_prompt)
            except Exception as exc:
                logger.debug("skill fragment lookup skipped: %s", exc)

        # Phase 6.9 — Append compact verbosity instruction for HAWK roles.
        # Prevents local Ollama models from generating verbose JSON that exhausts
        # the output token budget. Non-HAWK roles are never affected.
        _agent_role = getattr(agent, "role", "") or ""
        if _agent_role in _HAWK_STEP_KEYS:
            from app.services.hawk_verbosity import render_verbosity_instruction as _rvi

            _hawk_mode = (getattr(agent, "tools_config", None) or {}).get(
                "hawk_output_mode", "compact"
            )
            system_prompt = f"{system_prompt}\n\n{_rvi(_hawk_mode)}"

        try:
            prompt_reg = PromptRegistryService(self.db)
            await prompt_reg.record(
                project_id=project_id,
                run_id=None,
                role=agent.role or "agent",
                task_type="prompt",
                prompt_text=prompt,
                system_text=system_prompt,
            )
        except Exception as exc:
            logger.warning("PromptRegistryService.record failed: %s", exc)

        output, meta = await run_with_fallback(
            agent, prompt=prompt, system_prompt=system_prompt, db=self.db
        )
        try:
            await CryptoPersistenceService(self.db).persist_agent_output(
                project_id=project_id,
                run_id=run_id,
                agent_role=agent.role,
                output_text=output,
            )
        except Exception as exc:
            from app.services.crypto_persistence import ProposalValidationError as _PVE

            if isinstance(exc, _PVE):
                meta["proposal_validation_error"] = exc.reason
                logger.warning(
                    "Trade proposal validation failed for run %s (role=%s): %s",
                    run_id,
                    agent.role,
                    exc.reason,
                )
            else:
                logger.warning("CryptoPersistenceService.persist_agent_output failed: %s", exc)
        if compaction_record is not None:
            meta["context_compaction_id"] = str(compaction_record.id)
            meta["context_memory_applied"] = True
        elif memory_block:
            meta["context_memory_applied"] = True

        # Record outcome for skill winrate tracking
        if active_skill_id is not None:
            try:
                from app.services.skill_version import SkillVersionService as _SV

                await _SV(self.db).record_outcome(
                    active_skill_id, success=bool(output and output.strip())
                )
            except Exception as exc:
                logger.debug("skill record_outcome skipped: %s", exc)

        # HAWK-only observability metadata — booleans and lengths only, no raw content.
        if getattr(agent, "role", "") in {"hawk_trend", "hawk_structure", "hawk_counter"}:
            try:
                from app.services.market_data_renderer import (
                    render_market_data_for_hawk as _rmdfh,
                )

                _md = context.get("market_data") or {}
                _injected_via = (
                    "explicit_prompt"
                    if "$market_data_hawk" in str(template)
                    else "compacted_memory"
                    if meta.get("context_memory_applied")
                    else "missing"
                )
                meta.update(
                    {
                        "market_data_injected_via": _injected_via,
                        "market_data_hawk_length": len(_rmdfh(_md)),
                        "prompt_total_length": len(prompt),
                        "indicators_present": bool(_md.get("indicators")),
                        "klines_present": any(
                            bool((v or {}).get("recent_candles"))
                            for v in (_md.get("indicators") or {}).values()
                        ),
                        "invalidation_inputs_present": bool(_md.get("indicators")),
                        "symbol_received": _md.get("symbol") or "",
                        "timeframe_received": list((_md.get("indicators") or {}).keys()),
                    }
                )

                # Reliability observability — booleans/scalars only, no raw payload.
                # max_tokens is the *intended* budget (mirrors model_fallback.py);
                # for ollama it is num_predict. This does NOT change the budget.
                _max_tokens = getattr(agent, "max_tokens", None) or 2048
                _reliab = assess_hawk_output_reliability(
                    output,
                    tokens_used=meta.get("tokens_used"),
                    max_tokens=_max_tokens,
                )
                meta.update(
                    {
                        "max_tokens": _max_tokens,
                        "num_predict": _max_tokens,
                        "invalid_json": _reliab["invalid_json"],
                        "output_truncated_detected": _reliab["output_truncated_detected"],
                        "reached_token_ceiling": _reliab["reached_token_ceiling"],
                        "parse_error": _reliab["parse_error"],
                    }
                )
                # Defaults overwritten later by the execute() retry/block path.
                meta.setdefault("retry_count", 0)
                meta.setdefault("retry_reason", None)
                meta.setdefault("block_reason", None)
                meta.setdefault("fallback_used", bool(meta.get("fallback_used")))
                meta.setdefault("fallback_reason", meta.get("fallback_from"))
            except Exception as _obs_exc:
                logger.debug("HAWK observability metadata skipped: %s", _obs_exc)

        # compile_proposal (trade_proposal agent) observability — booleans/scalars only, no
        # raw payloads. Classification reuses the deterministic directional validator and does
        # NOT change any pass/fail behavior; it only records what the proposal/prompt looked like.
        if getattr(agent, "role", "") == "trade_proposal":
            try:
                meta.update(compile_proposal_observability(output, str(template), context))
                # runtime/model/fallback already populated by run_with_fallback; ensure presence.
                meta.setdefault("fallback_used", False)
                # Phase 4: warn (non-blocking) when decision-path step ran on last-resort model.
                _last_resort_model = "openai/gpt-oss-120b:free"
                _on_last_resort = meta.get("model") == _last_resort_model or bool(
                    meta.get("fallback_used")
                )
                meta["decision_path_on_last_resort"] = _on_last_resort
                if _on_last_resort:
                    logger.warning(
                        "[%s] compile_proposal ran on last-resort model=%s fallback_used=%s — "
                        "majority alignment enforced by deterministic validator regardless",
                        self._htrace(run_id) if hasattr(self, "_htrace") else "?",
                        meta.get("model"),
                        meta.get("fallback_used"),
                    )
            except Exception as _obs_exc:
                logger.debug("compile_proposal observability metadata skipped: %s", _obs_exc)

        return output, meta

    async def _run_kb_search(
        self, project_id: UUID, config: dict, context: dict
    ) -> tuple[str, dict]:
        query = self._substitute(
            str(config.get("query") or config.get("prompt") or config.get("label") or ""), context
        ).strip()

        # ── Lesson-scoped retrieval (honors source_type_filter) ────────────────────────
        # When a step declares source_type_filter (e.g. check_trade_lessons →
        # "trade_lesson"), route through the canonical TradeLearningService retrieval so the
        # result is scoped to that source_type AND the run's symbol. The returned text is
        # ADVISORY prompt context only — it sets no gate flag, approval, risk_ack,
        # validation_only, order param, or execution outcome.
        source_type_filter = str(config.get("source_type_filter") or "").strip()
        if source_type_filter:
            from app.services.trade_learning_service import TradeLearningService

            symbol = (
                str(
                    config.get("symbol")
                    or (context.get("input_payload") or {}).get("symbol")
                    or ""
                )
                .strip()
                .upper()
                or None
            )
            limit = int(config.get("top_k", 5) or 5)
            try:
                lessons = await TradeLearningService(self.db).get_relevant_lessons(
                    project_id, symbol=symbol, limit=limit, source_type=source_type_filter
                )
            except Exception as exc:
                # Retrieval must never fail the run nor bypass a gate. Degrade to a safe
                # empty advisory; downstream deterministic gates are unaffected.
                logger.warning("lesson retrieval failed, returning empty advisory: %s", exc)
                lessons = []
            scope = symbol or "this project"
            if not lessons:
                return f"No past {source_type_filter} entries found for {scope}.", {
                    "runtime": "kb_search",
                    "matches": 0,
                    "source_type_filter": source_type_filter,
                    "symbol": symbol,
                    "advisory": True,
                    "tokens_used": None,
                }
            lines = [
                f"Found {len(lessons)} past {source_type_filter} "
                f"entr{'y' if len(lessons) == 1 else 'ies'} for {scope} (advisory only):"
            ]
            for lesson in lessons:
                snippet = (lesson.get("content") or "")[:500]
                lines.append(f"\n### {lesson.get('title')}\n{snippet}")
            return "\n".join(lines), {
                "runtime": "kb_search",
                "matches": len(lessons),
                "source_type_filter": source_type_filter,
                "symbol": symbol,
                "doc_ids": [lesson.get("id") for lesson in lessons],
                "advisory": True,
                "tokens_used": None,
            }

        docs = []
        try:
            dna = DNAMemoryService(self.db)
            docs = await dna.get_relevant(
                project_id,
                query,
                max_entries=config.get("top_k", 5),
            )
        except Exception as exc:
            logger.warning(
                "DNAMemoryService.get_relevant failed, falling back to knowledge_repo: %s", exc
            )

        if not docs:
            # Fallback to unscored knowledge_repo search.
            search = query or None
            docs_fallback, total = await knowledge_repo.list_by_project(
                self.db, project_id=project_id, limit=10, search=search
            )
            if not docs_fallback:
                return f"No knowledge documents matched query: {query!r}", {
                    "runtime": "kb_search",
                    "matches": 0,
                    "tokens_used": None,
                }
            lines = [f"Found {len(docs_fallback)} of {total} matching documents:"]
            for doc in docs_fallback:
                snippet = (doc.content or "")[:500]
                lines.append(f"\n### {doc.title}\n{snippet}")
            return "\n".join(lines), {
                "runtime": "kb_search",
                "matches": len(docs_fallback),
                "doc_ids": [str(d.id) for d in docs_fallback],
                "tokens_used": None,
            }

        lines = [f"Found {len(docs)} matching documents:"]
        for doc in docs:
            snippet = (doc.content or "")[:500]
            lines.append(f"\n### {doc.title}\n{snippet}")
        return "\n".join(lines), {
            "runtime": "kb_search",
            "matches": len(docs),
            "doc_ids": [str(d.id) for d in docs],
            "tokens_used": None,
        }

    async def _run_write_note(
        self, project_id: UUID, config: dict, context: dict
    ) -> tuple[str, dict]:
        content = self._substitute(
            str(config.get("content") or config.get("text") or "$last_output"), context
        )
        if not content.strip():
            content = context.get("last_output") or ""
        title = self._substitute(
            str(config.get("title") or config.get("label") or "Workflow Output"), context
        )[:500]
        doc = await knowledge_repo.create(
            self.db,
            project_id=project_id,
            title=title,
            content=content,
            tags=["workflow-output"],
            source_type="output",
        )
        return f"Saved note '{title}' to knowledge base.", {
            "runtime": "write_note",
            "doc_id": str(doc.id),
            "tokens_used": None,
        }

    async def _run_http_request(self, config: dict, context: dict) -> tuple[str, dict]:
        method = str(config.get("method", "GET")).upper()
        url = self._substitute(str(config.get("url", "")), context)
        url = url.replace("{{last_output}}", str(context.get("last_output", "")))
        headers: dict = config.get("headers") or {}
        body: dict = config.get("body") or {}
        params: dict = config.get("params") or {}

        if method == "POST":
            result = await http_post(url, body=body, headers=headers)
        else:
            result = await http_get(url, headers=headers, params=params)

        output = result["data"]
        output_text = (
            json.dumps(output, ensure_ascii=False)
            if isinstance(output, (dict, list))
            else str(output)
        )
        return output_text, {
            "status_code": result["status_code"],
            "ok": result["ok"],
            "runtime": "http_request",
        }

    async def _run_market_data(self, config: dict, context: dict) -> tuple[str, dict]:
        """Fetch live market data + compute indicators; inject into context['market_data']."""
        from app.agents.tools.exchange_tool import get_fear_greed, get_klines, get_market_data
        from app.services.indicators import compute_all

        raw_symbol = config.get("symbol") or (context.get("input_payload") or {}).get("symbol")
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol:
            raise ValueError("market_data step: symbol is missing from config and input_payload")
        intervals: list[str] = list(config.get("intervals") or ["4h", "1h", "1d"])

        market: dict = await get_market_data(symbol)
        fear_greed: dict = await get_fear_greed()

        klines_data: dict[str, dict] = {}
        for interval in intervals:
            limit = 200 if interval == "1d" else 100
            klines = await get_klines(symbol, interval=interval, limit=limit)
            klines_data[interval] = compute_all(klines, include_recent_candles=True)

        result: dict = {
            "symbol": symbol,
            "price": market.get("price"),
            "funding_rate": market.get("funding_rate"),
            "long_short_ratio": market.get("long_short_ratio"),
            "fear_greed": fear_greed,
            "indicators": klines_data,
            "errors": market.get("errors", []),
        }
        try:
            price_value = float(result["price"])
        except (TypeError, ValueError):
            price_value = 0.0
        if price_value <= 0:
            raise ValueError(f"market_data step: exchange returned non-positive price for {symbol}")
        context["market_data"] = result
        output_text = json.dumps(result, ensure_ascii=False)
        return output_text, {"runtime": "market_data", "symbol": symbol, "tokens_used": None}

    async def _run_position_monitor(self, project_id: UUID, context: dict) -> tuple[str, dict]:
        """Build the exchange-driven position snapshot; inject it into context['monitor_snapshot'].

        This is the real source of truth for close detection: it polls the exchange (demo/
        testnet) per open position. The snapshot is consumed by the post-run hook
        (PositionLifecycleService.finalize_from_snapshot) and injected into the following LLM
        Position-Monitor prompt via $monitor_snapshot for interpretation/reporting only.
        """
        from app.crypto.services.position_monitor import PositionMonitor

        snapshot = await PositionMonitor(self.db).build_snapshot(project_id)
        context["monitor_snapshot"] = snapshot
        output_text = json.dumps(snapshot, ensure_ascii=False)
        return output_text, {
            "runtime": "position_monitor",
            "position_count": len(snapshot),
            "tokens_used": None,
        }

    async def _run_conditional(self, config: dict, context: dict) -> tuple[str, dict]:
        """Evaluate a condition against last_output. Returns 'true' or 'false'."""
        condition_type = config.get("condition_type", "contains")
        value = str(config.get("value", "")).lower()
        last_output = str(context.get("last_output", "")).lower()

        if condition_type == "contains":
            result = value in last_output
        elif condition_type == "not_contains":
            result = value not in last_output
        elif condition_type == "equals":
            result = last_output.strip() == value.strip()
        elif condition_type == "starts_with":
            result = last_output.strip().startswith(value)
        else:
            result = value in last_output

        return ("true" if result else "false"), {
            "condition_type": condition_type,
            "value": value,
            "result": result,
        }

    async def _run_hawk_vote(self, run_id: UUID, config: dict, context: dict) -> tuple[str, dict]:
        """Enforce a code-level 2/3 directional majority across the three HAWK agents.

        Data quality fields (sources_used, data_quality, market_data_snapshot, price deviation) are
        recorded as per-step warnings in dq_flags but do NOT null out valid votes. Only structural
        failures (step missing, status != completed, unparseable JSON, vote not in valid set) count
        as invalid_steps and block the gate.
        """
        source_steps = config.get("source_steps") or [
            "hawk_trend",
            "hawk_structure",
            "hawk_counter",
        ]
        normalized_steps = [str(step) for step in source_steps if str(step).strip()]

        # Reference price from fetch_market_data step (may be None if not available).
        ref_price: float | None = None
        try:
            ref_price = float((context.get("market_data") or {}).get("price") or 0) or None
        except (TypeError, ValueError):
            ref_price = None

        # Input market data quality — used to cross-validate HAWK data_quality claims.
        _input_md = context.get("market_data") or {}
        _input_indicators_ok = bool(_input_md.get("indicators"))
        _input_klines_ok = any(
            bool((v or {}).get("recent_candles"))
            for v in (_input_md.get("indicators") or {}).values()
        )
        _md_input_quality = (
            "FULL"
            if (_input_indicators_ok and _input_klines_ok)
            else "PARTIAL"
            if _input_indicators_ok
            else "MISSING"
        )

        steps, _ = await run_repo.list_steps_by_run(self.db, run_id=run_id, limit=500)
        by_key = {step.step_key: step for step in steps}

        # Build secondary index: agent name in output JSON → step (for workflows where
        # step keys are generic like "step_2" but outputs carry an "agent" field).
        by_agent_name: dict[str, object] = {}
        for s in steps:
            if s.status == "completed" and isinstance(s.output_json, dict):
                raw = s.output_json.get("output")
                if isinstance(raw, str):
                    parsed = extract_json_object(raw)
                    if parsed and isinstance(parsed.get("agent"), str):
                        by_agent_name[parsed["agent"].lower()] = s

        votes: dict[str, str | None] = {}
        invalid_steps: list[str] = []
        dq_flags: dict[str, list[str]] = {}
        now_utc = datetime.now(UTC)

        for step_key in normalized_steps:
            step = by_key.get(step_key) or by_agent_name.get(step_key.lower())
            if step is None or step.status != "completed" or not isinstance(step.output_json, dict):
                invalid_steps.append(step_key)
                votes[step_key] = None
                continue

            output_text = step.output_json.get("output")
            if not isinstance(output_text, str) or not output_text.strip():
                invalid_steps.append(step_key)
                votes[step_key] = None
                continue

            payload = extract_json_object(output_text)
            if payload is None:
                invalid_steps.append(step_key)
                votes[step_key] = None
                continue

            vote = payload.get("vote")
            vote_text = str(vote).upper() if isinstance(vote, str) else None
            if vote_text not in {"BULLISH", "BEARISH", "NEUTRAL"}:
                invalid_steps.append(step_key)
                votes[step_key] = None
                continue

            # ── Data quality checks (non-blocking warnings only) ─────────────
            step_dq: list[str] = []

            sources_used = payload.get("sources_used")
            if not sources_used:
                step_dq.append("no_sources")

            if str(payload.get("data_quality", "")).upper() not in ("REAL_MARKET_DATA", "REAL"):
                step_dq.append(f"not_real_market_data({payload.get('data_quality', 'missing')})")
            elif _md_input_quality != "FULL":
                # HAWK claimed REAL_MARKET_DATA but the injected input lacked full indicators.
                step_dq.append(f"claimed_real_but_input_was_{_md_input_quality}")

            snapshot = payload.get("market_data_snapshot")
            if not snapshot:
                step_dq.append("no_market_data_snapshot")
            elif ref_price is not None:
                try:
                    snap_price = float(
                        snapshot.get("price")
                        or snapshot.get("last_price")
                        or snapshot.get("close")
                        or 0
                    )
                    if snap_price > 0:
                        deviation = abs(snap_price - ref_price) / ref_price
                        if deviation > 0.05:
                            step_dq.append(
                                f"price_mismatch(snapshot={snap_price},ref={ref_price},dev={deviation:.1%})"
                            )
                except (TypeError, ValueError):
                    pass

            if step_dq:
                dq_flags[step_key] = step_dq
                logger.info(
                    "[%s] hawk_dq_warn step=%s flags=%s",
                    self._htrace(run_id),
                    step_key,
                    step_dq,
                )

            votes[step_key] = vote_text

        tally = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
        for vote in votes.values():
            if vote in tally:
                tally[vote] += 1

        allowed_majority = next(
            (direction for direction in ("BULLISH", "BEARISH") if tally[direction] >= 2),
            None,
        )
        gate_passed = not invalid_steps and allowed_majority is not None

        # Pre-check: directional votes must carry a numeric invalidation_level.
        # Done here (where DB-loaded payloads are available) so context is not required.
        missing_invalidation_levels: list[str] = []
        invalidation_levels: dict[str, float | None] = {}
        for _step_key in normalized_steps:
            _vote = votes.get(_step_key)
            if _vote not in ("BULLISH", "BEARISH"):
                continue
            _step = by_key.get(_step_key) or by_agent_name.get(_step_key.lower())
            _raw = (
                (_step.output_json.get("output", "") if isinstance(_step.output_json, dict) else "")
                if _step is not None
                else ""
            )
            _payload_check = extract_json_object(_raw) or {}
            _level = _payload_check.get("invalidation_level")
            try:
                invalidation_levels[_step_key] = float(_level)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                invalidation_levels[_step_key] = None
                missing_invalidation_levels.append(_step_key)

        # Reported direction: majority when gate passes; plurality (including NEUTRAL) when blocked;
        # NO_MAJORITY on a true tie (all equal) or all-invalid.
        if allowed_majority is not None:
            reported_direction = allowed_majority
        else:
            _max_count = max(tally.values())
            if _max_count == 0:
                reported_direction = "NO_MAJORITY"
            else:
                _top = [d for d, c in tally.items() if c == _max_count]
                reported_direction = _top[0] if len(_top) == 1 else "NO_MAJORITY"

        if invalid_steps:
            gate_reason = (
                "HAWK vote gate blocked: missing or invalid HAWK outputs for "
                + ", ".join(invalid_steps)
            )
        elif allowed_majority is None:
            gate_reason = "HAWK vote gate blocked: no 2/3 directional majority across HAWK agents"
        else:
            gate_reason = None

        result = {
            "agent": "hawk_vote_gate",
            "evaluated_at": now_utc.isoformat(),
            "source_steps": normalized_steps,
            "votes": votes,
            "vote_tally": tally,
            "majority_direction": reported_direction,
            "majority_count": tally.get(allowed_majority or "", 0),
            "gate_passed": gate_passed,
            "gate_result": "PASSED" if gate_passed else "BLOCKED",
            "gate_reason": gate_reason,
            "invalid_steps": invalid_steps,
            "dq_flags": dq_flags,
            "data_quality_failed_steps": [],
            "data_quality_reasons": {},
            "md_input_quality": _md_input_quality,
        }
        return json.dumps(result, ensure_ascii=False), {
            "runtime": "hawk_vote",
            "gate_passed": gate_passed,
            "majority_direction": reported_direction,
            "majority_count": tally.get(allowed_majority or "", 0),
            "invalid_steps": invalid_steps,
            "dq_flags": dq_flags,
            "data_quality_failed_steps": [],
            "data_quality_reasons": {},
            "gate_reason": gate_reason,
            "missing_invalidation_levels": missing_invalidation_levels,
            "invalidation_levels": invalidation_levels,
            "md_input_quality": _md_input_quality,
            "tokens_used": None,
        }

    async def _run_sub_workflow(
        self, project_id: UUID, config: dict, context: dict
    ) -> tuple[str, dict]:
        """Execute another workflow synchronously and return its output."""
        import uuid as _uuid

        from app.db.session import get_worker_db_context
        from app.schemas.run import RunCreate
        from app.services.run import RunService

        sub_workflow_id_str = config.get("workflow_id")
        if not sub_workflow_id_str:
            return ("sub_workflow: no workflow_id configured", {"error": "missing workflow_id"})

        try:
            sub_workflow_id = _uuid.UUID(str(sub_workflow_id_str))
        except ValueError:
            return (
                f"sub_workflow: invalid workflow_id '{sub_workflow_id_str}'",
                {"error": "invalid uuid"},
            )

        # Recursion guards — without these a self/cyclic sub_workflow recurses until the
        # Celery hard kill and leaves the run stuck 'running' (a permanent schedule jam).
        if self._depth >= _MAX_SUB_WORKFLOW_DEPTH:
            return (
                f"sub_workflow: max nesting depth {_MAX_SUB_WORKFLOW_DEPTH} exceeded",
                {"error": "max_depth_exceeded", "depth": self._depth},
            )
        if sub_workflow_id in self._visited_workflows:
            return (
                f"sub_workflow: cycle detected — workflow {sub_workflow_id} already in the chain",
                {"error": "cycle_detected", "workflow_id": str(sub_workflow_id)},
            )

        # Run the sub-workflow in its OWN db session. Sharing self.db let the sub-run's
        # commits flush the parent run's in-flight transaction at arbitrary points.
        async with get_worker_db_context() as sub_db:
            run_svc = RunService(sub_db)
            sub_run = await run_svc.create(
                project_id=project_id,
                data=RunCreate(
                    workflow_id=sub_workflow_id,
                    trigger="sub_workflow",
                    input_payload_json={"parent_output": context.get("last_output", "")},
                ),
            )
            await sub_db.commit()
            sub_executor = RunExecutor(
                sub_db,
                _depth=self._depth + 1,
                _visited_workflows=self._visited_workflows | {sub_workflow_id},
            )
            completed_sub = await sub_executor.execute(sub_run.id, project_id)
            output = completed_sub.output_text or ""
            return (output, {"sub_run_id": str(sub_run.id), "sub_status": completed_sub.status})

    async def _run_coin_screener(
        self, project_id: UUID, config: dict, context: dict
    ) -> tuple[str, dict]:
        """Step kind 'coin_screener' — rank liquid USDT pairs and dispatch the trade pipeline per coin.

        Pure price-math pre-filter (no LLM): pick the top-N coins by liquidity x momentum, drop coins
        we already hold, respect the global open-position cap, then create one trade-pipeline run per
        survivor with input_payload={"symbol": ...}. Each run is dispatched to a Celery worker so the
        pipelines execute independently in parallel.
        """
        import os

        from sqlalchemy import func, or_, select

        from app.agents.tools.exchange_tool import screen_usdt_symbols
        from app.db.models.crypto_trading import Position
        from app.schemas.run import RunCreate
        from app.services.run import RunService
        from app.worker.celery_app import celery_app

        top_n = int(config.get("top_n", 5))
        min_quote_volume = float(config.get("min_quote_volume", 5_000_000.0))
        blacklist = list(config.get("blacklist") or [])
        target_workflow_name = str(config.get("target_workflow_name") or "").strip()
        max_open = int(os.getenv("KILL_SWITCH_MAX_OPEN_POSITIONS", "3"))

        # Optional exclusion config (backward-compatible: absent → prior behavior).
        exclude_open_positions = bool(config.get("exclude_open_positions", True))
        exclude_workflow_names = [
            str(name) for name in (config.get("exclude_symbols_from_workflows") or [])
        ]
        exclude_recent_minutes = int(config.get("exclude_recent_runs_minutes") or 0)
        max_dispatch_cfg = config.get("max_dispatch")
        max_dispatch = int(max_dispatch_cfg) if max_dispatch_cfg is not None else None

        if not target_workflow_name:
            return (
                "coin_screener: no target_workflow_name configured",
                {"error": "missing target_workflow_name"},
            )

        # Resolve the trade-pipeline workflow by name within this project.
        workflows, _ = await workflow_repo.list_workflows_by_project(
            self.db, project_id=project_id, limit=500
        )
        target = next((w for w in workflows if w.name == target_workflow_name), None)
        if target is None:
            return (
                f"coin_screener: target workflow '{target_workflow_name}' not found",
                {"error": "workflow_not_found", "target_workflow_name": target_workflow_name},
            )

        # Current global open-position count (across all symbols) for the cap.
        open_count = int(
            await self.db.scalar(
                select(func.count()).where(
                    Position.project_id == project_id, Position.status == "OPEN"
                )
            )
            or 0
        )
        slots = max(0, max_open - open_count)

        # Symbols reserved by other workflows: active runs (always) and, if configured,
        # runs created within the recent window. Active takes priority over recent.
        exclude_reason_by_symbol: dict[str, str] = {}
        active_statuses = ("queued", "running", "waiting_approval", "paused", "blocked")
        if exclude_workflow_names:
            excluded_wf_ids = [w.id for w in workflows if w.name in exclude_workflow_names]
            if excluded_wf_ids:
                active_clause = Run.status.in_(active_statuses)
                if exclude_recent_minutes > 0:
                    cutoff = datetime.now(UTC) - timedelta(minutes=exclude_recent_minutes)
                    reserved_clause = or_(active_clause, Run.created_at >= cutoff)
                else:
                    reserved_clause = active_clause
                rows = (
                    await self.db.execute(
                        select(Run.input_payload_json, Run.status).where(
                            Run.project_id == project_id,
                            Run.workflow_id.in_(excluded_wf_ids),
                            reserved_clause,
                        )
                    )
                ).all()
                for payload, status in rows:
                    symbol = (payload or {}).get("symbol")
                    if not symbol:
                        continue
                    reason = (
                        "active_run_in_excluded_workflow"
                        if status in active_statuses
                        else "recent_run_in_excluded_workflow"
                    )
                    # Active wins over recent if the same symbol shows up in both.
                    if (
                        symbol not in exclude_reason_by_symbol
                        or reason == "active_run_in_excluded_workflow"
                    ):
                        exclude_reason_by_symbol[symbol] = reason

        candidates = await screen_usdt_symbols(
            top_n=top_n, min_quote_volume=min_quote_volume, blacklist=blacklist
        )
        ranked_symbols = [c["symbol"] for c in candidates]

        svc = CryptoPersistenceService(self.db)
        run_svc = RunService(self.db)
        dispatched: list[str] = []
        skipped: list[str] = []
        for cand in candidates:
            symbol = cand["symbol"]
            if symbol in exclude_reason_by_symbol:
                skipped.append(symbol)
                continue
            if exclude_open_positions and await svc.has_open_position(project_id, symbol):
                exclude_reason_by_symbol[symbol] = "open_position"
                skipped.append(symbol)
                continue
            if len(dispatched) >= slots:
                exclude_reason_by_symbol[symbol] = "global_cap_reached"
                skipped.append(symbol)
                continue
            if max_dispatch is not None and len(dispatched) >= max_dispatch:
                exclude_reason_by_symbol[symbol] = "max_dispatch_reached"
                skipped.append(symbol)
                continue
            run = await run_svc.create(
                project_id=project_id,
                data=RunCreate(
                    workflow_id=target.id,
                    trigger="screener",
                    input_payload_json={
                        "symbol": symbol,
                        "timeframe": "4h",
                        "project_mode": effective_project_mode(),
                    },
                ),
            )
            try:
                celery_app.send_task(
                    "app.worker.tasks.execute_run", args=[str(run.id), str(project_id)]
                )
            except Exception as exc:
                logger.warning("coin_screener dispatch failed for %s: %s", symbol, exc)
                continue
            dispatched.append(symbol)

        excluded_symbols = sorted(exclude_reason_by_symbol.keys())
        meta = {
            # Legacy keys (kept so existing consumers keep working).
            "considered": ranked_symbols,
            "dispatched": dispatched,
            "skipped_open_position": [
                s for s, r in exclude_reason_by_symbol.items() if r == "open_position"
            ],
            "open_positions": open_count,
            "max_open_positions": max_open,
            "slots_available": slots,
            "target_workflow": target_workflow_name,
            # Observability keys for the dual-screener exclusion logic.
            "ranked_symbols": ranked_symbols,
            "dispatched_symbols": dispatched,
            "skipped_symbols": skipped,
            "excluded_symbols": excluded_symbols,
            "exclude_reason_by_symbol": exclude_reason_by_symbol,
            "target_workflow_name": target_workflow_name,
        }
        summary = (
            f"Screener: {len(candidates)} candidates, dispatched {len(dispatched)} "
            f"({', '.join(dispatched) or 'none'}); skipped {len(skipped)}; "
            f"{open_count}/{max_open} positions open."
        )
        return (summary, meta)

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _consume_consecutive_loss_ack(
        self,
        project_id: UUID,
        plan: ExecutionPlan,
        execution: object,
        order_result: dict,
    ) -> None:
        """Burn the single-use consecutive-loss ack — iff it cleared the gate AND a real entry
        order placed.

        Safe to call unconditionally: a no-op when the gate was not cleared by an ack, when the
        exchange call FAILED (no order), or when no ``order_id`` came back. ``consume_ack`` itself
        is also a no-op when no valid ack exists. A status of SUCCESS or ENTRY_FILLED_SL_FAILED
        both mean the entry order reached the exchange (the order happened), so the override is
        burned — only an outright FAILED entry (or a preflight block before this point) preserves
        it for a legitimate retry.
        """
        if not getattr(plan, "consecutive_loss_ack_used", False):
            return
        if getattr(execution, "execution_status", None) == "FAILED" or not order_result.get(
            "order_id"
        ):
            return
        from app.services import risk_ack

        if await risk_ack.consume_ack(self.db, project_id):
            await self.db.flush()
            logger.info(
                "[risk_ack] consumed single-use consecutive-loss ack for project %s after order %s",
                project_id,
                order_result.get("order_id"),
            )

    async def _run_exchange_execute(self, project_id: UUID, run_id: UUID) -> tuple[str, dict]:
        """Step kind 'exchange_execute' — place a real order via exchange_tool.place_order().

        Looks up the APPROVED proposal for this run (set by the human_approval_gate step),
        then calls place_order() which respects EXCHANGE_MODE env var (paper/testnet/live).
        Returns a JSON string summary and a meta dict.
        """
        import json as _json

        from sqlalchemy import select as _select

        from app.agents.tools.exchange_tool import place_order
        from app.db.models.crypto_trading import (
            Position,
            TradeExecution,
            TradeJournal,
            TradeProposal,
        )

        result = await self.db.execute(
            _select(TradeProposal)
            .where(
                TradeProposal.project_id == project_id,
                TradeProposal.run_id == run_id,
                TradeProposal.status == "APPROVED",
            )
            .order_by(TradeProposal.created_at.desc())
            .limit(1)
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            msg = "EXCHANGE_EXECUTE_SKIPPED: no APPROVED proposal for this run"
            return msg, {"runtime": "exchange_execute", "skipped": True}

        try:
            plan = await prepare_execution_plan(
                db=self.db,
                project_id=project_id,
                proposal=proposal,
                require_status="APPROVED",
            )
        except ExecutionPreflightError as exc:
            proposal.status = "REJECTED"
            proposal.rejection_reason = str(exc)
            await self.db.flush()
            return f"EXCHANGE_EXECUTE_BLOCKED: {exc}", {
                "runtime": "exchange_execute",
                "error": "execution_preflight_failed",
            }

        order_result = await place_order(
            symbol=proposal.symbol,
            side=plan.side,
            amount=plan.amount,
            order_type="market",
            price=plan.entry_price,
            stop_loss=proposal.stop_loss,
            take_profits=plan.take_profits,
            notional_usdt=plan.size_usdt,
        )

        execution = TradeExecution(
            project_id=project_id,
            proposal_id=proposal.id,
            exchange=str(order_result.get("exchange", "unknown")),
            order_id=order_result.get("order_id"),
            symbol=proposal.symbol,
            side=proposal.direction.upper(),
            executed_price=self._as_float_safe(order_result.get("executed_price")),
            size=self._as_float_safe(order_result.get("size")) or plan.amount,
            sl_order_id=order_result.get("sl_order_id"),
            tp_order_ids=order_result.get("tp_order_ids") or [],
            execution_status=str(order_result.get("execution_status", "FAILED")),
            error_message=order_result.get("error"),
            raw_response=order_result,
        )
        self.db.add(execution)
        await self.db.flush()
        logger.info(
            "[%s] execution_persisted id=%s status=%s mode=%s",
            self._htrace(run_id),
            execution.id,
            execution.execution_status,
            order_result.get("mode", "-"),
        )

        # Single-use consume of the consecutive-loss override (mirrors ExecutionService): if this
        # trade only cleared the consecutive-loss gate via an explicit acknowledgement, burn it now
        # that a real entry order has been placed on the exchange — so it authorizes exactly one
        # attempt. Consume only when an order actually reached the exchange (order_id present and
        # status != FAILED); a preflight block or a failed exchange call leaves the ack intact for a
        # legitimate retry. Done before Position/journal persistence so a downstream error can't
        # leave a consumed-but-unrecorded ack reusable.
        await self._consume_consecutive_loss_ack(project_id, plan, execution, order_result)

        meta: dict = {
            "runtime": "exchange_execute",
            "exchange_mode": order_result.get("mode", "UNKNOWN"),
            "order_id": order_result.get("order_id"),
            "execution_status": execution.execution_status,
        }

        if execution.execution_status == "SUCCESS":
            position = Position(
                project_id=project_id,
                execution_id=execution.id,
                symbol=proposal.symbol,
                side=proposal.direction.upper(),
                entry_price=execution.executed_price or plan.entry_price,
                current_price=execution.executed_price or plan.entry_price,
                size=execution.size or plan.amount,
                stop_loss=proposal.stop_loss,
                take_profits=plan.take_profits,
                status="OPEN",
            )
            self.db.add(position)
            await self.db.flush()

            journal = TradeJournal(
                project_id=project_id,
                position_id=position.id,
                symbol=proposal.symbol,
                direction=proposal.direction.upper(),
                entry_price=execution.executed_price or plan.entry_price,
                size=execution.size or plan.amount,
                result="OPEN",
                original_thesis=proposal.full_proposal_md or proposal.news_summary,
                agent_votes=proposal.agent_vote_summary or {},
                news_used=[proposal.news_summary] if proposal.news_summary else [],
                raw_facts=build_trade_journal_raw_facts(
                    proposal=proposal,
                    execution_payload=order_result,
                    position_id=position.id,
                    journal_action="exchange_execute_step",
                    entry_price=execution.executed_price or plan.entry_price,
                    size=execution.size or plan.amount,
                ),
                decision_log=[
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "action": "exchange_execute_step",
                        "entry_price": execution.executed_price or plan.entry_price,
                        "order_id": order_result.get("order_id"),
                        "exchange": order_result.get("exchange"),
                    }
                ],
            )
            self.db.add(journal)
            proposal.status = "EXECUTED"
            await self.db.flush()
            logger.info(
                "[%s] journal_persisted journal_id=%s position_id=%s proposal_id=%s",
                self._htrace(run_id),
                journal.id,
                position.id,
                proposal.id,
            )
            meta["position_id"] = str(position.id)
            summary = _json.dumps(
                {
                    "execution_mode": order_result.get("mode"),
                    "symbol": proposal.symbol,
                    "side": plan.side,
                    "executed_price": execution.executed_price,
                    "amount": plan.amount,
                    "order_id": order_result.get("order_id"),
                    "sl_order_id": order_result.get("sl_order_id"),
                    "tp_order_ids": order_result.get("tp_order_ids"),
                    "execution_status": "SUCCESS",
                    "position_id": str(position.id),
                    "exchange": order_result.get("exchange"),
                }
            )
        else:
            proposal.status = "EXECUTION_FAILED"
            await self.db.flush()
            summary = _json.dumps(
                {
                    "execution_status": "FAILED",
                    "error": order_result.get("error"),
                    "exchange_mode": order_result.get("mode"),
                    "symbol": proposal.symbol,
                }
            )

        return summary, meta

    def _evaluate_boundary_handoff(
        self, *, step_key: str, next_step_key: str | None, output_text: str
    ) -> str | None:
        """Return a fail-closed message when a boundary contract is violated."""

        for contract in contracts_for_handoff(step_key, next_step_key):
            result = validate_handoff(output_text, contract)
            if result.passed:
                continue
            missing = ", ".join(result.missing_fields) or "unknown"
            parse_error = f" parse_error={result.parse_error}." if result.parse_error else ""
            return (
                f"Handoff contract '{contract.name}' failed "
                f"(schema={contract.schema_version}) from '{step_key}' to '{next_step_key}': "
                f"missing required fields [{missing}].{parse_error}"
            )
        return None

    async def _auto_execute_trade_proposal(self, project_id: UUID, run_id: UUID) -> str:
        """Find the PENDING_APPROVAL proposal for this run, auto-approve, and execute it."""
        from sqlalchemy import select as _select

        from app.agents.tools.exchange_tool import place_order
        from app.db.models.crypto_trading import (
            Position,
            TradeExecution,
            TradeJournal,
            TradeProposal,
        )

        result = await self.db.execute(
            _select(TradeProposal)
            .where(
                TradeProposal.project_id == project_id,
                TradeProposal.run_id == run_id,
                TradeProposal.status == "PENDING_APPROVAL",
            )
            .order_by(TradeProposal.created_at.desc())
            .limit(1)
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            return "AUTO_EXECUTE_SKIPPED: no PENDING_APPROVAL proposal for this run"

        proposal.status = "APPROVED"
        proposal.approved_at = datetime.now(UTC)
        await self.db.flush()

        try:
            plan = await prepare_execution_plan(
                db=self.db,
                project_id=project_id,
                proposal=proposal,
                require_status="APPROVED",
            )
        except ExecutionPreflightError as exc:
            proposal.status = "REJECTED"
            proposal.rejection_reason = str(exc)
            await self.db.flush()
            return f"AUTO_EXECUTE_BLOCKED: {exc}"

        order_result = await place_order(
            symbol=proposal.symbol,
            side=plan.side,
            amount=plan.amount,
            order_type="market",
            price=plan.entry_price,
            stop_loss=proposal.stop_loss,
            take_profits=plan.take_profits,
            notional_usdt=plan.size_usdt,
        )

        execution = TradeExecution(
            project_id=project_id,
            proposal_id=proposal.id,
            exchange=str(order_result.get("exchange", "paper_trade")),
            order_id=order_result.get("order_id"),
            symbol=proposal.symbol,
            side=proposal.direction.upper(),
            executed_price=self._as_float_safe(order_result.get("executed_price")),
            size=self._as_float_safe(order_result.get("size")) or plan.amount,
            sl_order_id=order_result.get("sl_order_id"),
            tp_order_ids=order_result.get("tp_order_ids") or [],
            execution_status=str(order_result.get("execution_status", "FAILED")),
            error_message=order_result.get("error"),
            raw_response=order_result,
        )
        self.db.add(execution)
        await self.db.flush()

        # Single-use consume of the consecutive-loss override — same contract as
        # _run_exchange_execute (consume only when a real entry order reached the exchange).
        await self._consume_consecutive_loss_ack(project_id, plan, execution, order_result)

        if execution.execution_status == "SUCCESS":
            position = Position(
                project_id=project_id,
                execution_id=execution.id,
                symbol=proposal.symbol,
                side=proposal.direction.upper(),
                entry_price=execution.executed_price or plan.entry_price,
                current_price=execution.executed_price or plan.entry_price,
                size=execution.size or plan.amount,
                stop_loss=proposal.stop_loss,
                take_profits=plan.take_profits,
                status="OPEN",
            )
            self.db.add(position)
            await self.db.flush()

            journal = TradeJournal(
                project_id=project_id,
                position_id=position.id,
                symbol=proposal.symbol,
                direction=proposal.direction.upper(),
                entry_price=execution.executed_price or plan.entry_price,
                size=execution.size or plan.amount,
                result="OPEN",
                original_thesis=proposal.full_proposal_md or proposal.news_summary,
                agent_votes=proposal.agent_vote_summary or {},
                news_used=[proposal.news_summary] if proposal.news_summary else [],
                raw_facts=build_trade_journal_raw_facts(
                    proposal=proposal,
                    execution_payload=order_result,
                    position_id=position.id,
                    journal_action="auto_executed",
                    entry_price=execution.executed_price or plan.entry_price,
                    size=execution.size or plan.amount,
                ),
                decision_log=[
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "action": "auto_executed",
                        "trigger": "winrate_gate",
                        "entry_price": execution.executed_price or plan.entry_price,
                    }
                ],
            )
            self.db.add(journal)
            proposal.status = "EXECUTED"
            await self.db.flush()
            _tp_levels = [
                tp if isinstance(tp, (int, float)) else tp.get("tp_level", tp)
                for tp in (plan.take_profits or [])
                if tp is not None
            ]
            return (
                f"AUTO_EXECUTED: {proposal.symbol} {proposal.direction} "
                f"@ {execution.executed_price or plan.entry_price} | "
                f"execution_id={execution.id} position_id={position.id} | "
                f"stop_loss={proposal.stop_loss} "
                f"take_profits={json.dumps(_tp_levels)} "
                f"position_size_usdt={plan.size_usdt} "
                f"execution_mode={order_result.get('mode', 'PAPER')}"
            )
        else:
            proposal.status = "EXECUTION_FAILED"
            await self.db.flush()
            return f"AUTO_EXECUTE_FAILED: {order_result.get('error', 'unknown error')}"

    @staticmethod
    def _entry_price_from_plan(entry_plan: object) -> float:
        return entry_price_from_plan(entry_plan)

    @staticmethod
    def _take_profit_levels_from_proposal(raw_levels: object) -> list[float]:
        return take_profit_levels_from_proposal(raw_levels)

    @staticmethod
    def _as_float_safe(value: object) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    async def _resolve_agent(self, project_id: UUID, agent_key: object) -> AgentConfig:
        agent: AgentConfig | None = None
        if agent_key:
            try:
                agent = await agent_config_repo.get_by_id(self.db, UUID(str(agent_key)))
            except (ValueError, TypeError):
                agent = None
        if agent is None or agent.project_id != project_id:
            # Fall back to the first active agent in the project.
            agents, _ = await agent_config_repo.list_by_project(
                self.db, project_id=project_id, limit=1
            )
            agent = agents[0] if agents else None
        if agent is None:
            raise NotFoundError(
                message="No agent available for step", details={"project_id": str(project_id)}
            )
        return agent

    @staticmethod
    def _substitute(template: str, context: dict) -> str:
        payload = context.get("input_payload") or {}
        try:
            payload_str = json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError):
            payload_str = str(payload)
        hawk_outputs = json.dumps(
            {
                k: context.get(f"{k}_output", "")
                for k in ("hawk_trend", "hawk_structure", "hawk_counter")
            },
            ensure_ascii=False,
        )
        market_data = context.get("market_data") or {}
        from app.services.market_data_renderer import render_market_data_for_hawk as _render_hawk_md

        # $market_data_hawk gets the full HAWK view (incl. recent_candles). Render it from the
        # complete dict BEFORE stripping candles for the lean $market_data view below.
        market_data_hawk_str = _render_hawk_md(market_data)

        # $market_data stays lean: recent_candles are a HAWK-only enrichment and must not bloat
        # the general-purpose $market_data token consumed by non-HAWK agents. Strip them from a
        # shallow copy only when present, leaving context["market_data"] itself untouched.
        _lean_md = market_data
        _indicators = market_data.get("indicators")
        if isinstance(_indicators, dict) and any(
            isinstance(v, dict) and "recent_candles" in v for v in _indicators.values()
        ):
            _lean_md = dict(market_data)
            _lean_md["indicators"] = {
                iv: (
                    {k: val for k, val in v.items() if k != "recent_candles"}
                    if isinstance(v, dict)
                    else v
                )
                for iv, v in _indicators.items()
            }
        try:
            market_data_str = json.dumps(_lean_md, ensure_ascii=False)
        except (TypeError, ValueError):
            market_data_str = str(_lean_md)
        monitor_snapshot = context.get("monitor_snapshot")
        if monitor_snapshot is None:
            monitor_snapshot_str = "[]"
        else:
            try:
                monitor_snapshot_str = json.dumps(monitor_snapshot, ensure_ascii=False)
            except (TypeError, ValueError):
                monitor_snapshot_str = str(monitor_snapshot)

        result = template.replace("$last_output", str(context.get("last_output") or ""))
        result = result.replace("$input_payload", payload_str)
        result = result.replace("$symbol", str(payload.get("symbol") or ""))
        result = result.replace("$project_name", str(context.get("project_name") or ""))
        result = result.replace("$project_slug", str(context.get("project_slug") or ""))
        result = result.replace("$hawk_vote_result", str(context.get("hawk_vote_result") or ""))
        result = result.replace(
            "$hawk_invalidation_levels", str(context.get("hawk_invalidation_levels") or "")
        )
        result = result.replace("$hawk_outputs", hawk_outputs)
        result = result.replace("$market_data_hawk", market_data_hawk_str)
        result = result.replace("$market_data", market_data_str)
        result = result.replace("$monitor_snapshot", monitor_snapshot_str)
        result = result.replace("$now", datetime.now(UTC).isoformat())
        result = result.replace("$run_id", str(context.get("run_id") or ""))
        result = result.replace("$market_type", str(context.get("market_type") or "futures"))
        return result

    async def _pause(
        self,
        run: Run,
        db_step: RunStep,
        idx: int,
        info: LLMErrorInfo,
        project_id: UUID,
        run_id: UUID,
        trace_id: UUID,
    ) -> Run:
        run.status = "paused"
        run.current_step_index = idx
        run.paused_at = datetime.now(UTC)
        run.pause_reason = info.error_type
        run.resume_policy = info.resume_policy
        run.recovery_count = (run.recovery_count or 0) + 1
        run.error_text = info.raw_message
        if info.retry_after_seconds > 0:
            run.retry_after_at = datetime.now(UTC) + timedelta(seconds=info.retry_after_seconds)
        db_step.status = "paused"
        db_step.output_json = {"error": info.raw_message, "error_type": info.error_type}
        await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
        await run_repo.update_run(self.db, db_run=run, update_data={})
        await self.db.commit()
        await self.tracer.emit(
            event_type="run.paused",
            project_id=project_id,
            run_id=run_id,
            trace_id=trace_id,
            summary=f"Paused: {info.error_type}",
            event_status="paused",
            payload={
                "resume_policy": info.resume_policy,
                "retry_after_seconds": info.retry_after_seconds,
            },
        )
        await self._emit(
            project_id,
            run_id,
            "run.paused",
            agent_name="orchestrator",
            data=f"Paused ({info.error_type})",
        )
        return run

    async def _block(
        self,
        run: Run,
        db_step: RunStep,
        message: str,
        project_id: UUID,
        run_id: UUID,
        trace_id: UUID,
        pause_reason: str = "hawk_vote_no_majority",
    ) -> Run:
        run.status = "blocked"
        run.error_text = message[:5000]
        run.pause_reason = pause_reason
        run.finished_at = datetime.now(UTC)
        run.output_text = message[:5000]
        await run_repo.update_run(self.db, db_run=run, update_data={})
        await self.db.commit()
        await self.tracer.emit(
            event_type="run.blocked",
            project_id=project_id,
            run_id=run_id,
            trace_id=trace_id,
            summary="Run blocked by workflow gate",
            event_status="blocked",
            payload={"error": message[:1000], "step_key": db_step.step_key},
        )
        await self._emit(
            project_id, run_id, "run.blocked", agent_name=db_step.step_key, data=message[:1000]
        )
        return run

    async def _fail(
        self,
        run: Run,
        db_step: RunStep,
        message: str,
        project_id: UUID,
        run_id: UUID,
        trace_id: UUID,
    ) -> Run:
        run.status = "failed"
        run.error_text = message[:5000]
        run.finished_at = datetime.now(UTC)
        db_step.status = "failed"
        db_step.output_json = {"error": message[:5000]}
        db_step.finished_at = datetime.now(UTC)
        await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
        await run_repo.update_run(self.db, db_run=run, update_data={})
        await self.db.commit()
        await self.tracer.emit(
            event_type="run.failed",
            project_id=project_id,
            run_id=run_id,
            trace_id=trace_id,
            summary="Run failed",
            event_status="failed",
            payload={"error": message[:1000]},
        )
        await self._emit(
            project_id, run_id, "run.failed", agent_name="orchestrator", data=message[:1000]
        )
        return run

    async def _load_run(self, run_id: UUID, project_id: UUID) -> Run:
        run = await run_repo.get_run_by_id(self.db, run_id)
        if not run or run.project_id != project_id:
            raise NotFoundError(message="Run not found", details={"run_id": str(run_id)})
        return run

    async def _load_steps(self, run: Run) -> list[dict]:
        return self._steps_from_definition(await self._load_workflow_definition(run))

    async def _load_workflow_definition(self, run: Run) -> dict:
        if run.workflow_id is None:
            return {}
        workflow = await workflow_repo.get_workflow_by_id(self.db, run.workflow_id)
        if workflow is None:
            return {}
        return workflow.definition_json or {}

    @staticmethod
    def _steps_from_definition(definition: dict) -> list[dict]:
        steps = definition.get("steps") or []
        return [s for s in steps if isinstance(s, dict)]

    @staticmethod
    def _next_step_key(steps: list[dict], idx: int) -> str | None:
        if idx + 1 >= len(steps):
            return None
        return str(steps[idx + 1].get("key") or f"step_{idx + 2}")

    @staticmethod
    def _validation_only_config(definition: dict, input_payload: dict) -> dict[str, object]:
        config = definition.get("config") if isinstance(definition.get("config"), dict) else {}
        sources = (
            ("workflow.definition_json.validation_only", definition.get("validation_only")),
            ("workflow.definition_json.stop_after_hawk", definition.get("stop_after_hawk")),
            ("workflow.definition_json.config.validation_only", config.get("validation_only")),
            ("workflow.definition_json.config.stop_after_hawk", config.get("stop_after_hawk")),
            ("run.input_payload.validation_only", input_payload.get("validation_only")),
            ("run.input_payload.stop_after_hawk", input_payload.get("stop_after_hawk")),
        )
        for source, value in sources:
            if value is True or (isinstance(value, str) and value.strip().lower() == "true"):
                return {"enabled": True, "source": source}
        stop_after_step = config.get("stop_after_step") or definition.get("stop_after_step")
        if isinstance(stop_after_step, str) and stop_after_step.strip() == "hawk_vote_gate":
            return {"enabled": True, "source": "workflow.definition_json.stop_after_step"}
        return {"enabled": False, "source": None}

    async def _get_or_create_step(self, run: Run, step_key: str, step_kind: str, step_def: dict):
        existing, _ = await run_repo.list_steps_by_run(self.db, run_id=run.id, limit=500)
        for step in existing:
            if step.step_key == step_key:
                return step
        agent_config_id = None
        config_inner = step_def.get("config") or {}
        agent_key = step_def.get("agent_key") or config_inner.get("agent_key")
        if agent_key:
            try:
                agent_config_id = UUID(str(agent_key))
            except (ValueError, TypeError):
                agent_config_id = None
        return await run_repo.create_run_step(
            self.db,
            run_id=run.id,
            step_key=step_key,
            step_kind=step_kind,
            agent_config_id=agent_config_id,
            input_json=step_def.get("config") or {},
        )

    async def _last_completed_output(self, run: Run) -> str:
        steps, _ = await run_repo.list_steps_by_run(self.db, run_id=run.id, limit=500)
        last = ""
        for step in steps:
            if step.status == "completed" and isinstance(step.output_json, dict):
                out = step.output_json.get("output")
                if isinstance(out, str):
                    last = out
        return last

    async def _workflow_context_items(self, run_id: UUID) -> list[dict[str, str]]:
        steps, _ = await run_repo.list_steps_by_run(self.db, run_id=run_id, limit=500)
        items: list[dict[str, str]] = []
        for step in steps:
            if step.status != "completed" or not isinstance(step.output_json, dict):
                continue
            output = step.output_json.get("output")
            if not isinstance(output, str) or not output.strip():
                continue
            items.append(
                {
                    "role": "workflow_step",
                    "label": step.step_key,
                    "content": output.strip(),
                }
            )
        return items

    @staticmethod
    def _trace_id(run: Run) -> UUID:
        """Stable per-run trace id (reuse summary store, else the run id)."""
        summary = run.runtime_summary or {}
        raw = summary.get("trace_id")
        if raw:
            try:
                return UUID(str(raw))
            except (ValueError, TypeError):
                pass
        return run.id

    @staticmethod
    def _htrace(run_id: UUID) -> str:
        """Short 8-char hex prefix for structured log correlation within a run."""
        return str(run_id).replace("-", "")[:8]

    @staticmethod
    def _check_hawk_invalidation_levels(
        gate_votes: dict[str, str],
        hawk_individual: dict[str, str],
    ) -> tuple[bool, list[str], dict[str, float | None]]:
        """Return (ok, missing_directional_steps, levels_by_step) for directional HAWK votes.

        Only BULLISH and BEARISH votes require a numeric invalidation_level.
        NEUTRAL votes are excluded — they carry no stop-loss implication.
        """
        missing: list[str] = []
        levels: dict[str, float | None] = {}
        for step_key, vote in gate_votes.items():
            if vote not in ("BULLISH", "BEARISH"):
                continue
            raw = hawk_individual.get(step_key) or ""
            try:
                parsed = extract_json_object(raw) or {}
            except Exception:
                parsed = {}
            level = parsed.get("invalidation_level")
            try:
                levels[step_key] = float(level)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                levels[step_key] = None
                missing.append(step_key)
        return (len(missing) == 0, missing, levels)

    async def _emit(
        self,
        project_id: UUID,
        run_id: UUID,
        event_type: str,
        *,
        agent_name: str = "",
        data: str = "",
    ) -> None:
        """Fan out an event to the in-memory event bus AND the room hub (best-effort)."""
        try:
            await event_bus.emit(
                AgentEvent(
                    type=event_type,
                    project_id=str(project_id),
                    run_id=str(run_id),
                    agent_name=agent_name,
                    data=data,
                )
            )
        except Exception:
            logger.debug("event_bus emit failed for %s", event_type)

        try:
            from app.api.routes.v1.rooms import room_hub

            await room_hub.broadcast(
                str(project_id),
                {
                    "type": "agent_message",
                    "event": event_type,
                    "run_id": str(run_id),
                    "agent": agent_name,
                    "message": data,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            logger.debug("room_hub broadcast failed for %s", event_type)
