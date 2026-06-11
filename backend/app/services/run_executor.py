"""Real workflow execution engine.

Loads a queued :class:`Run`, walks its workflow's ``definition_json["steps"]``,
dispatches each step to a runtime adapter (or knowledge/approval handler),
streams events to the in-memory event bus + room hub, and persists step output.

Quota / rate-limit / transient errors pause the run (with ``retry_after_at``)
instead of failing it, so a recovery worker can resume later. Auth errors pause
with ``resume_policy="manual_token_fix"``.
"""

import json
import logging
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
from app.services.crypto_persistence import CryptoPersistenceService
from app.services.dna_memory import DNAMemoryService
from app.services.event_bus import AgentEvent, event_bus
from app.services.handoff_contracts import DEFAULT_CONTRACTS, check_handoff
from app.services.llm_error_classifier import LLMErrorInfo, classify_llm_error
from app.services.metrics_tracker import MetricsTracker
from app.services.model_fallback import run_with_fallback
from app.services.obsidian_exporter import export_step as obsidian_export
from app.services.prompt_registry import PromptRegistryService
from app.services.trace_emitter import TraceEmitter

logger = logging.getLogger(__name__)

# Step keys that are HAWK analysis agents — used for retry and context tracking.
_HAWK_STEP_KEYS: frozenset[str] = frozenset({"hawk_trend", "hawk_structure", "hawk_counter"})


def _extract_pnl_pct(text: str) -> float | None:
    """Extract realized PnL% from journal/execution output. Returns None if not found."""
    import re
    for pat in (r'"pnl_pct"\s*:\s*(-?[\d.]+)', r'pnl[_%\s]+(-?[\d.]+)%', r'realized.*?(-?[\d.]+)%'):
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
        r'confidence[_\s]score[:\s]+(\d+)',
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return min(int(m.group(1)), 100)
    return 0


class RunExecutor:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.tracer = TraceEmitter(db)
        self.metrics = MetricsTracker(db)

    # ── Public API ──────────────────────────────────────────────────────────

    async def execute(self, run_id: UUID, project_id: UUID) -> Run:
        run = await self._load_run(run_id, project_id)
        project = await project_repo.get_by_id(self.db, project_id)
        project_name = project.name if project else ""
        project_slug = (project.slug if project else "") or ""

        steps = await self._load_steps(run)
        trace_id = self._trace_id(run)

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
                    await self._emit(project_id, run_id, "run.step_completed", agent_name=step_key,
                                     data=f"Auto-approved (confidence={confidence}≥{threshold})")
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
                    await self._emit(project_id, run_id, "run.waiting_approval", agent_name=step_key,
                                     data=f"Confidence={confidence}<{threshold}: awaiting human approval")
                    return run

            # ── Winrate auto-trade gate: auto-execute if project winrate >= threshold ──
            if step_kind == "winrate_trade_gate":
                threshold = float((config or {}).get("winrate_threshold", 80.0))
                winrate = await CryptoPersistenceService(self.db).get_project_winrate(project_id)
                if winrate >= threshold:
                    auto_result = await self._auto_execute_trade_proposal(project_id, run_id)
                    db_step.status = "completed"
                    db_step.output_json = {
                        "output": auto_result,
                        "meta": {"winrate": winrate, "threshold": threshold, "auto_executed": True},
                    }
                    db_step.finished_at = datetime.now(UTC)
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    # skip human_approval_gate + execute_trade (already done above)
                    skip_count = int((config or {}).get("skip_steps_on_auto", 2))
                    idx += skip_count
                    context["last_output"] = auto_result
                    context["auto_trade_executed"] = True
                    await self._emit(
                        project_id, run_id, "run.step_completed", agent_name=step_key,
                        data=f"Auto-executed (winrate={winrate:.1f}% ≥ {threshold}%)",
                    )
                    idx += 1
                    run.current_step_index = idx
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    continue
                else:
                    db_step.status = "waiting_approval"
                    run.status = "waiting_approval"
                    run.current_step_index = idx
                    run.paused_at = datetime.now(UTC)
                    run.pause_reason = "approval"
                    await run_repo.update_run_step(self.db, db_step=db_step, update_data={})
                    await run_repo.update_run(self.db, db_run=run, update_data={})
                    await self.db.commit()
                    await self._emit(
                        project_id, run_id, "run.waiting_approval", agent_name=step_key,
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
                return await self._fail(run, db_step, str(exc), project_id, run_id, trace_id)

            tokens = step_meta.get("tokens_used")
            if isinstance(tokens, int):
                total_tokens += tokens

            # Re-run HAWK analysis steps if output is empty or not valid JSON.
            # The workflow waits — data completeness matters more than speed.
            if step_kind == "prompt" and step_key in _HAWK_STEP_KEYS:
                _retry = 0
                while _retry < 2 and (not output_text.strip() or extract_json_object(output_text) is None):
                    _retry += 1
                    logger.warning("HAWK step '%s' returned invalid output — retry %d/2", step_key, _retry)
                    await self._emit(
                        project_id, run_id, "run.step_retry", agent_name=step_key,
                        data=f"{step_key}: output missing or not JSON, retrying ({_retry}/2)",
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

            # Soft handoff-contract quality gate (warning only — never blocks the run).
            try:
                for contract in DEFAULT_CONTRACTS:
                    if step_kind in contract.source_step_kinds:
                        passed, missing = check_handoff(output_text, contract)
                        if not passed:
                            logger.warning(
                                "Handoff contract '%s' not satisfied — missing: %s",
                                contract.name,
                                missing,
                            )
                            await self._emit(
                                project_id,
                                run_id,
                                "run.handoff_warning",
                                agent_name=step_key,
                                data=f"Quality gate '{contract.name}': missing concepts {missing}",
                            )
            except Exception as exc:
                logger.warning("Handoff contract check failed: %s", exc)

            context["last_output"] = output_text

            # Keep individual HAWK outputs in context so SAGE can read each one.
            if step_kind == "prompt" and step_key in _HAWK_STEP_KEYS:
                context[f"{step_key}_output"] = output_text

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
                # Invalid steps mean a runtime error (API failure, bad output) caused the
                # gate to fail — not a legitimate trading-signal block. Treat as failed.
                if step_meta.get("invalid_steps"):
                    return await self._fail(
                        run,
                        db_step,
                        gate_message,
                        project_id,
                        run_id,
                        trace_id,
                    )
                # Build vote breakdown for display
                votes: dict = step_meta.get("votes") or {}
                tally: dict = step_meta.get("vote_tally") or {}
                if votes:
                    vote_lines = " | ".join(f"{k}: {v}" for k, v in votes.items())
                    tally_line = f"BULLISH {tally.get('BULLISH', 0)} / BEARISH {tally.get('BEARISH', 0)} / NEUTRAL {tally.get('NEUTRAL', 0)}"
                    gate_message = f"{gate_message}\n{vote_lines}\nTally: {tally_line}"
                return await self._block(
                    run,
                    db_step,
                    gate_message,
                    project_id,
                    run_id,
                    trace_id,
                )

            # Build $hawk_vote_result: vote-gate tally + each HAWK's full JSON output.
            # SAGE needs the individual outputs to verify invalidation_level per hawk.
            if _is_hawk_gate and bool(step_meta.get("gate_passed")):
                hawk_individual = {
                    k: context.get(f"{k}_output", "")
                    for k in ("hawk_trend", "hawk_structure", "hawk_counter")
                }
                context["hawk_vote_result"] = json.dumps(
                    {"vote_gate": output_text, "hawk_outputs": hawk_individual},
                    ensure_ascii=False,
                )

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

        # ── Post-trade learning: extract P&L and store KB lesson on loss ──
        try:
            from app.services.trade_learning_service import TradeLearningService
            last_out = context.get("last_output", "")
            pnl = _extract_pnl_pct(last_out)
            if pnl is not None:
                await TradeLearningService(self.db).trigger_post_trade_learning(
                    project_id=project_id, run_id=run_id, pnl_pct=pnl
                )
        except Exception as exc:
            logger.warning("TradeLearningService failed: %s", exc)

        return run

    async def resume_approved(self, run_id: UUID, project_id: UUID) -> Run:
        """Approve a waiting run: skip the approval step and continue."""
        run = await self._load_run(run_id, project_id)
        if run.status != "waiting_approval":
            raise NotFoundError(
                message="Run is not awaiting approval",
                details={"run_id": str(run_id), "status": run.status},
            )
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

        try:
            await self.metrics.record_review_cycle(run_id)
        except Exception as exc:
            logger.warning("MetricsTracker.record_review_cycle failed: %s", exc)

        return await self.execute(run_id, project_id)

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
                return await self._run_hawk_vote(run_id, config)
            return await self._run_conditional(config, context)
        if step_kind == "loop":
            # Loop control is handled in execute() — just return iteration info.
            iter_count = context.get(f"_loop_{config.get('step_key', 'loop')}", 0)
            return (f"loop_iteration_{iter_count}", {})
        if step_kind == "hawk_vote":
            return await self._run_hawk_vote(run_id, config)
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

        output, meta = await run_with_fallback(agent, prompt=prompt, system_prompt=system_prompt, db=self.db)
        try:
            await CryptoPersistenceService(self.db).persist_agent_output(
                project_id=project_id,
                run_id=run_id,
                agent_role=agent.role,
                output_text=output,
            )
        except Exception as exc:
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

        return output, meta

    async def _run_kb_search(
        self, project_id: UUID, config: dict, context: dict
    ) -> tuple[str, dict]:
        query = self._substitute(
            str(config.get("query") or config.get("prompt") or config.get("label") or ""), context
        ).strip()

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

    async def _run_hawk_vote(self, run_id: UUID, config: dict) -> tuple[str, dict]:
        """Enforce a code-level 2/3 directional majority across the three HAWK agents."""
        source_steps = config.get("source_steps") or [
            "hawk_trend",
            "hawk_structure",
            "hawk_counter",
        ]
        normalized_steps = [str(step) for step in source_steps if str(step).strip()]

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
            "evaluated_at": datetime.now(UTC).isoformat(),
            "source_steps": normalized_steps,
            "votes": votes,
            "vote_tally": tally,
            "majority_direction": allowed_majority or "NO_MAJORITY",
            "majority_count": tally.get(allowed_majority or "", 0),
            "gate_passed": gate_passed,
            "gate_result": "PASSED" if gate_passed else "BLOCKED",
            "gate_reason": gate_reason,
            "invalid_steps": invalid_steps,
        }
        return json.dumps(result, ensure_ascii=False), {
            "runtime": "hawk_vote",
            "gate_passed": gate_passed,
            "majority_direction": allowed_majority or "NO_MAJORITY",
            "majority_count": tally.get(allowed_majority or "", 0),
            "invalid_steps": invalid_steps,
            "gate_reason": gate_reason,
            "tokens_used": None,
        }

    async def _run_sub_workflow(
        self, project_id: UUID, config: dict, context: dict
    ) -> tuple[str, dict]:
        """Execute another workflow synchronously and return its output."""
        import uuid as _uuid

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

        run_svc = RunService(self.db)
        sub_run = await run_svc.create(
            project_id=project_id,
            data=RunCreate(
                workflow_id=sub_workflow_id,
                trigger="sub_workflow",
                input_payload_json={"parent_output": context.get("last_output", "")},
            ),
        )

        sub_executor = RunExecutor(self.db)
        completed_sub = await sub_executor.execute(sub_run.id, project_id)

        output = completed_sub.output_text or ""
        return (output, {"sub_run_id": str(sub_run.id), "sub_status": completed_sub.status})

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _run_exchange_execute(self, project_id: UUID, run_id: UUID) -> tuple[str, dict]:
        """Step kind 'exchange_execute' — place a real order via exchange_tool.place_order().

        Looks up the APPROVED proposal for this run (set by the human_approval_gate step),
        then calls place_order() which respects EXCHANGE_MODE env var (paper/testnet/live).
        Returns a JSON string summary and a meta dict.
        """
        import json as _json
        from sqlalchemy import select as _select
        from app.db.models.crypto_trading import Position, TradeExecution, TradeJournal, TradeProposal
        from app.agents.tools.exchange_tool import place_order

        result = await self.db.execute(
            _select(TradeProposal).where(
                TradeProposal.project_id == project_id,
                TradeProposal.run_id == run_id,
                TradeProposal.status == "APPROVED",
            ).order_by(TradeProposal.created_at.desc()).limit(1)
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            msg = "EXCHANGE_EXECUTE_SKIPPED: no APPROVED proposal for this run"
            return msg, {"runtime": "exchange_execute", "skipped": True}

        entry_price = self._entry_price_from_plan(proposal.entry_plan)
        if entry_price <= 0:
            proposal.status = "EXECUTION_FAILED"
            await self.db.flush()
            return "EXCHANGE_EXECUTE_FAILED: invalid entry price", {"runtime": "exchange_execute", "error": "invalid_entry_price"}

        take_profits = self._take_profit_levels_from_proposal(proposal.take_profit)
        amount = round(float(proposal.position_size_usdt or 40) / entry_price, 8)
        side = "buy" if proposal.direction.upper() == "LONG" else "sell"

        order_result = await place_order(
            symbol=proposal.symbol,
            side=side,
            amount=amount,
            order_type="market",
            price=entry_price,
            stop_loss=proposal.stop_loss,
            take_profits=take_profits,
        )

        execution = TradeExecution(
            project_id=project_id,
            proposal_id=proposal.id,
            exchange=str(order_result.get("exchange", "unknown")),
            order_id=order_result.get("order_id"),
            symbol=proposal.symbol,
            side=proposal.direction.upper(),
            executed_price=self._as_float_safe(order_result.get("executed_price")),
            size=self._as_float_safe(order_result.get("size")) or amount,
            sl_order_id=order_result.get("sl_order_id"),
            tp_order_ids=order_result.get("tp_order_ids") or [],
            execution_status=str(order_result.get("execution_status", "FAILED")),
            error_message=order_result.get("error"),
            raw_response=order_result,
        )
        self.db.add(execution)
        await self.db.flush()

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
                entry_price=execution.executed_price or entry_price,
                current_price=execution.executed_price or entry_price,
                size=execution.size or amount,
                stop_loss=proposal.stop_loss,
                take_profits=take_profits,
                status="OPEN",
            )
            self.db.add(position)
            await self.db.flush()

            journal = TradeJournal(
                project_id=project_id,
                position_id=position.id,
                symbol=proposal.symbol,
                direction=proposal.direction.upper(),
                entry_price=execution.executed_price or entry_price,
                size=execution.size or amount,
                result="OPEN",
                original_thesis=proposal.full_proposal_md or proposal.news_summary,
                agent_votes=proposal.agent_vote_summary or {},
                news_used=[proposal.news_summary] if proposal.news_summary else [],
                decision_log=[{
                    "timestamp": datetime.now(UTC).isoformat(),
                    "action": "exchange_execute_step",
                    "entry_price": execution.executed_price or entry_price,
                    "order_id": order_result.get("order_id"),
                    "exchange": order_result.get("exchange"),
                }],
            )
            self.db.add(journal)
            proposal.status = "EXECUTED"
            await self.db.flush()
            meta["position_id"] = str(position.id)
            summary = _json.dumps({
                "execution_mode": order_result.get("mode"),
                "symbol": proposal.symbol,
                "side": side,
                "executed_price": execution.executed_price,
                "amount": amount,
                "order_id": order_result.get("order_id"),
                "sl_order_id": order_result.get("sl_order_id"),
                "tp_order_ids": order_result.get("tp_order_ids"),
                "execution_status": "SUCCESS",
                "position_id": str(position.id),
                "exchange": order_result.get("exchange"),
            })
        else:
            proposal.status = "EXECUTION_FAILED"
            await self.db.flush()
            summary = _json.dumps({
                "execution_status": "FAILED",
                "error": order_result.get("error"),
                "exchange_mode": order_result.get("mode"),
                "symbol": proposal.symbol,
            })

        return summary, meta

    async def _auto_execute_trade_proposal(self, project_id: UUID, run_id: UUID) -> str:
        """Find the PENDING_APPROVAL proposal for this run, auto-approve, and execute it."""
        from sqlalchemy import select as _select
        from app.db.models.crypto_trading import Position, TradeExecution, TradeJournal, TradeProposal
        from app.agents.tools.exchange_tool import place_order
        from app.services.kill_switch import KillSwitch

        result = await self.db.execute(
            _select(TradeProposal).where(
                TradeProposal.project_id == project_id,
                TradeProposal.run_id == run_id,
                TradeProposal.status == "PENDING_APPROVAL",
            ).order_by(TradeProposal.created_at.desc()).limit(1)
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            return "AUTO_EXECUTE_SKIPPED: no PENDING_APPROVAL proposal for this run"

        proposal.status = "APPROVED"
        proposal.approved_at = datetime.now(UTC)
        await self.db.flush()

        entry_price = self._entry_price_from_plan(proposal.entry_plan)
        if entry_price <= 0:
            proposal.status = "EXECUTION_FAILED"
            await self.db.flush()
            return "AUTO_EXECUTE_FAILED: invalid entry price in proposal"

        take_profits = self._take_profit_levels_from_proposal(proposal.take_profit)

        ks = KillSwitch(self.db)
        ks_result = await ks.check(
            project_id=project_id,
            symbol=proposal.symbol,
            direction=proposal.direction,
            stop_loss=proposal.stop_loss,
            take_profit_levels=take_profits,
            proposed_size_usdt=float(proposal.position_size_usdt or 0),
            entry_price=entry_price,
            market_regime="NEUTRAL",
        )
        if not ks_result.passed:
            proposal.status = "REJECTED"
            proposal.rejection_reason = "Kill switch blocked auto-exec: " + "; ".join(ks_result.blocked_reasons)
            await self.db.flush()
            return f"AUTO_EXECUTE_BLOCKED: {'; '.join(ks_result.blocked_reasons)}"

        size_usdt = ks_result.adjusted_position_size_usdt or float(proposal.position_size_usdt or 0)
        if size_usdt <= 0:
            return "AUTO_EXECUTE_FAILED: position size is zero after kill switch"

        amount = round(size_usdt / entry_price, 8)
        side = "buy" if proposal.direction.upper() == "LONG" else "sell"

        order_result = await place_order(
            symbol=proposal.symbol,
            side=side,
            amount=amount,
            order_type="market",
            price=entry_price,
            stop_loss=proposal.stop_loss,
            take_profits=take_profits,
        )

        execution = TradeExecution(
            project_id=project_id,
            proposal_id=proposal.id,
            exchange=str(order_result.get("exchange", "paper_trade")),
            order_id=order_result.get("order_id"),
            symbol=proposal.symbol,
            side=proposal.direction.upper(),
            executed_price=self._as_float_safe(order_result.get("executed_price")),
            size=self._as_float_safe(order_result.get("size")) or amount,
            sl_order_id=order_result.get("sl_order_id"),
            tp_order_ids=order_result.get("tp_order_ids") or [],
            execution_status=str(order_result.get("execution_status", "FAILED")),
            error_message=order_result.get("error"),
            raw_response=order_result,
        )
        self.db.add(execution)
        await self.db.flush()

        if execution.execution_status == "SUCCESS":
            position = Position(
                project_id=project_id,
                execution_id=execution.id,
                symbol=proposal.symbol,
                side=proposal.direction.upper(),
                entry_price=execution.executed_price or entry_price,
                current_price=execution.executed_price or entry_price,
                size=execution.size or amount,
                stop_loss=proposal.stop_loss,
                take_profits=take_profits,
                status="OPEN",
            )
            self.db.add(position)
            await self.db.flush()

            journal = TradeJournal(
                project_id=project_id,
                position_id=position.id,
                symbol=proposal.symbol,
                direction=proposal.direction.upper(),
                entry_price=execution.executed_price or entry_price,
                size=execution.size or amount,
                result="OPEN",
                original_thesis=proposal.full_proposal_md or proposal.news_summary,
                agent_votes=proposal.agent_vote_summary or {},
                news_used=[proposal.news_summary] if proposal.news_summary else [],
                decision_log=[{
                    "timestamp": datetime.now(UTC).isoformat(),
                    "action": "auto_executed",
                    "trigger": "winrate_gate",
                    "entry_price": execution.executed_price or entry_price,
                }],
            )
            self.db.add(journal)
            proposal.status = "EXECUTED"
            await self.db.flush()
            return (
                f"AUTO_EXECUTED: {proposal.symbol} {proposal.direction} "
                f"@ {execution.executed_price or entry_price} | "
                f"execution_id={execution.id} position_id={position.id}"
            )
        else:
            proposal.status = "EXECUTION_FAILED"
            await self.db.flush()
            return f"AUTO_EXECUTE_FAILED: {order_result.get('error', 'unknown error')}"

    @staticmethod
    def _entry_price_from_plan(entry_plan: object) -> float:
        if not isinstance(entry_plan, dict):
            return 0.0
        for key in ("primary_entry", "entry", "price", "avg_entry", "target_entry", "entry_zone_high", "entry_zone_low"):
            try:
                value = float(entry_plan.get(key) or 0)
                if value > 0:
                    return value
            except (TypeError, ValueError):
                continue
        levels = entry_plan.get("levels")
        if isinstance(levels, list) and levels:
            try:
                value = float(levels[0])
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
        return 0.0

    @staticmethod
    def _take_profit_levels_from_proposal(raw_levels: object) -> list[float]:
        values: list[float] = []
        for item in raw_levels or []:
            try:
                if isinstance(item, dict):
                    candidate = item.get("tp_level") or item.get("price") or item.get("target") or item.get("level")
                else:
                    candidate = item
                if candidate is not None:
                    value = float(candidate)
                    if value > 0:
                        values.append(value)
            except (TypeError, ValueError):
                continue
        return values

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
            {k: context.get(f"{k}_output", "") for k in ("hawk_trend", "hawk_structure", "hawk_counter")},
            ensure_ascii=False,
        )
        result = template.replace("$last_output", str(context.get("last_output") or ""))
        result = result.replace("$input_payload", payload_str)
        result = result.replace("$project_name", str(context.get("project_name") or ""))
        result = result.replace("$project_slug", str(context.get("project_slug") or ""))
        result = result.replace("$hawk_vote_result", str(context.get("hawk_vote_result") or ""))
        result = result.replace("$hawk_outputs", hawk_outputs)
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
    ) -> Run:
        run.status = "blocked"
        run.error_text = message[:5000]
        run.pause_reason = "hawk_vote_no_majority"
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
        if run.workflow_id is None:
            return []
        workflow = await workflow_repo.get_workflow_by_id(self.db, run.workflow_id)
        if workflow is None:
            return []
        definition = workflow.definition_json or {}
        steps = definition.get("steps") or []
        return [s for s in steps if isinstance(s, dict)]

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
