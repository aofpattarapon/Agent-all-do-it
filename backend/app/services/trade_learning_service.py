"""Trade Learning Service — stores trade mistakes as KB entries and retrieves
them before new trades to prevent repeating errors."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.json_utils import extract_json_object
from app.core.project_paths import project_vault_dir
from app.db.models.crypto_trading import TradeJournal
from app.db.models.project import KnowledgeDocument
from app.repositories import agent_config as agent_config_repo
from app.repositories import knowledge_repo, run_repo

if TYPE_CHECKING:
    from app.services.position_lifecycle import ClosedTrade

logger = logging.getLogger(__name__)

# Role of the already-seeded agent that performs post-trade reflection.
_REFLECTION_AGENT_ROLE = "post_trade_review"

# Namespaced facet prefixes used for filterable lesson tags. These coexist with
# the legacy bare tags (``trade_lesson`` / ``BTCUSDT`` / ``loss`` / ``win``) so old
# documents and old retrieval filters keep working unchanged.
_FACET_PREFIXES: tuple[str, ...] = ("symbol", "outcome", "direction", "timeframe", "market", "workflow")
_KNOWN_TIMEFRAMES: frozenset[str] = frozenset(
    {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"}
)


def _norm_direction(value: str | None) -> str:
    """Normalise a trade direction to ``long`` / ``short`` / ``unknown`` (never fabricated)."""
    v = (value or "").strip().lower()
    if v in {"long", "buy", "bull", "bullish"}:
        return "long"
    if v in {"short", "sell", "bear", "bearish"}:
        return "short"
    return "unknown"


def _norm_timeframe(value: str | None) -> str:
    """Normalise a timeframe to a known interval string, else ``unknown``."""
    v = (value or "").strip().lower()
    return v if v in _KNOWN_TIMEFRAMES else "unknown"


def _norm_market(value: str | None) -> str:
    """Normalise a market type to ``futures`` / ``spot`` / ``unknown``."""
    v = (value or "").strip().lower()
    if v in {"futures", "usdm_futures", "perp", "perpetual"}:
        return "futures"
    if v == "spot":
        return "spot"
    return "unknown"


def _norm_workflow(value: str | None) -> str:
    """Normalise a workflow kind to ``auto_30m`` / ``auto_15m`` / ``manual`` / ``unknown``."""
    v = (value or "").strip().lower().replace(" ", "_")
    if v in {"auto_30m", "auto_15m", "manual"}:
        return v
    return "unknown"


def _derive_workflow_timeframe(workflow_name: str | None) -> tuple[str, str]:
    """Map a workflow display name to a (workflow_kind, timeframe) pair.

    Grounded only — an unrecognised or empty name yields ``unknown`` values rather
    than guessing. The Auto pipelines carry their cadence in the name.
    """
    name = (workflow_name or "").strip().lower()
    if not name:
        return "unknown", "unknown"
    if "auto 30m" in name or "auto_30m" in name:
        return "auto_30m", "30m"
    if "auto 15m" in name or "auto_15m" in name:
        return "auto_15m", "15m"
    # Any other named (e.g. manual proposal-to-execution) pipeline: kind is manual,
    # but the candle timeframe is not encoded in the name → unknown (not fabricated).
    return "manual", "unknown"


def _current_market_type() -> str:
    """Resolve the active market type from the same env var the exchange routing uses."""
    return _norm_market(os.getenv("MARKET_TYPE", "futures"))


def _build_lesson_tags(
    symbol: str,
    pnl_pct: float,
    direction: str | None,
    timeframe: str | None,
    market: str | None,
    workflow: str | None,
    strategy: str | None = None,
) -> list[str]:
    """Build the lesson tag list: legacy bare tags + additive namespaced facet tags.

    Backward compatibility is preserved by always emitting the original
    ``trade_lesson`` / ``<SYMBOL>`` / ``loss|win`` tags alongside the new
    ``facet:value`` tags. Missing facets become an explicit ``:unknown`` sentinel —
    they are never fabricated. Order is preserved and duplicates removed.
    """
    sym = (symbol or "UNKNOWN").strip().upper() or "UNKNOWN"
    outcome = "loss" if pnl_pct < 0 else "win"
    direction_v = _norm_direction(direction)
    timeframe_v = _norm_timeframe(timeframe)
    market_v = _norm_market(market)
    workflow_v = _norm_workflow(workflow)

    tags: list[str] = [
        # ── legacy bare tags (unchanged contract) ──
        "trade_lesson",
        sym,
        outcome,
        # ── additive namespaced facet tags ──
        f"symbol:{sym}",
        f"outcome:{outcome}",
        f"direction:{direction_v}",
        f"timeframe:{timeframe_v}",
        f"market:{market_v}",
        f"workflow:{workflow_v}",
    ]
    if strategy:
        strategy_v = str(strategy).strip().lower()
        if strategy_v:
            tags.append(f"strategy:{strategy_v}")

    seen: set[str] = set()
    deduped: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    return deduped


def _build_lesson_content(
    trade_id: UUID,
    symbol: str,
    pattern: str,
    agent_votes: dict,
    outcome: str,
    pnl_pct: float,
    error_summary: str,
    *,
    direction: str = "unknown",
    timeframe: str = "unknown",
    market: str = "unknown",
    workflow: str = "unknown",
    strategy: str | None = None,
) -> str:
    """Build a structured Markdown document for a trade lesson.

    High-cardinality identifiers and numeric/structured facets live in the body —
    in particular a machine-readable ``lesson-meta`` fenced block — never as tags.
    """
    pnl_label = f"{pnl_pct:+.2f}%"
    vote_lines = (
        "\n".join(f"  - **{agent}**: {vote}" for agent, vote in agent_votes.items())
        if agent_votes
        else "  - (no agent votes recorded)"
    )
    lesson_meta = {
        "trade_id": str(trade_id),
        "symbol": (symbol or "UNKNOWN").strip().upper() or "UNKNOWN",
        "outcome": "loss" if pnl_pct < 0 else "win",
        "close_reason": outcome,
        "direction": _norm_direction(direction),
        "timeframe": _norm_timeframe(timeframe),
        "market": _norm_market(market),
        "workflow": _norm_workflow(workflow),
        "strategy": (str(strategy).strip().lower() if strategy else ""),
        "pnl_pct": round(pnl_pct, 4),
    }
    meta_json = json.dumps(lesson_meta, ensure_ascii=False, sort_keys=True)

    return f"""# Trade Lesson: {symbol} — {outcome}

## Summary
- **Symbol**: {symbol}
- **Trade ID**: {trade_id}
- **Outcome**: {outcome}
- **P&L**: {pnl_label}
- **Recorded at**: {datetime.now(UTC).isoformat()}

## Error / Observation
{error_summary}

## Market Pattern at Entry
{pattern}

## Agent Votes
{vote_lines}

## Key Takeaway
{"This trade resulted in a loss. Review the pattern and agent consensus before entering similar setups." if pnl_pct < 0 else "This trade was profitable. Document what worked well for future reference."}

## Machine Metadata
```lesson-meta
{meta_json}
```
"""


class TradeLearningService:
    """Stores trade outcomes as KnowledgeDocument entries and retrieves
    relevant lessons before a trade is placed."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record_lesson(
        self,
        project_id: UUID,
        trade_id: UUID,
        error_summary: str,
        symbol: str,
        pattern: str,
        agent_votes: dict,
        outcome: str,
        pnl_pct: float,
        *,
        direction: str | None = None,
        timeframe: str | None = None,
        market_type: str | None = None,
        workflow: str | None = None,
        strategy: str | None = None,
    ) -> None:
        """Persist a trade lesson as a KnowledgeDocument and a vault .md file.

        Args:
            project_id: Project owning the trade.
            trade_id: UUID of the trade record for cross-reference.
            error_summary: Human-readable description of what went wrong (or right).
            symbol: e.g. "BTCUSDT".
            pattern: Short description of the market pattern at entry.
            agent_votes: Dict of {agent_name: "BUY"|"SELL"|"HOLD"}.
            outcome: e.g. "TP", "SL", "MANUAL_CLOSE" (recorded as ``close_reason``).
            pnl_pct: Realised P&L percentage (negative = loss).
            direction: "long"/"short" when known; ``None`` → ``direction:unknown`` tag.
            timeframe: candle timeframe (e.g. "30m") when grounded; else ``unknown``.
            market_type: "futures"/"spot" when known; else ``unknown``.
            workflow: workflow kind ("auto_30m"/"auto_15m"/"manual") when grounded; else ``unknown``.
            strategy: optional grounded strategy label (e.g. "hawk_sage"); omitted when falsy.

        Backward compatibility: legacy bare tags (``trade_lesson``/``<SYMBOL>``/``loss``/``win``)
        are always retained; new namespaced facet tags are additive. This method never sets,
        weakens or bypasses any deterministic safety gate — lessons are advisory context only.
        """
        tags = _build_lesson_tags(
            symbol=symbol,
            pnl_pct=pnl_pct,
            direction=direction,
            timeframe=timeframe,
            market=market_type,
            workflow=workflow,
            strategy=strategy,
        )
        title = f"Trade Lesson: {symbol} {outcome}"
        content = _build_lesson_content(
            trade_id=trade_id,
            symbol=symbol,
            pattern=pattern,
            agent_votes=agent_votes,
            outcome=outcome,
            pnl_pct=pnl_pct,
            error_summary=error_summary,
            direction=_norm_direction(direction),
            timeframe=_norm_timeframe(timeframe),
            market=_norm_market(market_type),
            workflow=_norm_workflow(workflow),
            strategy=strategy,
        )

        # Persist to DB via knowledge repo
        await knowledge_repo.create(
            self._db,
            project_id=project_id,
            title=title,
            content=content,
            tags=tags,
            source_type="trade_lesson",
        )

        # Also write a Markdown file to the project vault for human review
        vault_dir = project_vault_dir(project_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"trade_lesson_{symbol}_{outcome}_{timestamp}_{str(trade_id)[:8]}.md"
        lesson_path = vault_dir / filename
        try:
            lesson_path.write_text(content, encoding="utf-8")
            logger.info("Trade lesson written to vault: %s", lesson_path)
        except OSError as exc:
            # Non-fatal — DB record is the source of truth
            logger.warning("Could not write lesson to vault file %s: %s", lesson_path, exc)

    def _facet_condition(self, facet: str, value: str, strict: bool):
        """Build a retrieval condition for one namespaced facet.

        Strict mode requires the document to carry the matching ``facet:value`` tag.
        Broad mode (default) additionally admits documents that carry *no* tag for this
        facet at all — so legacy/partially-tagged lessons are never hidden by a filter.
        ``facet`` is always an internal whitelist constant (never caller input), so the
        jsonpath prefix string is safe to interpolate.
        """
        match = KnowledgeDocument.tags.contains([f"{facet}:{value}"])
        if strict:
            return match
        # Inline the jsonpath as an untyped SQL literal so PostgreSQL coerces it to the
        # ``jsonpath`` type (a bound text param is rejected as varchar). ``facet`` is an
        # internal whitelist constant — never caller input — so this is injection-safe.
        path_literal = literal_column(f"'$[*] ? (@ starts with \"{facet}:\")'")
        has_facet = func.jsonb_path_exists(KnowledgeDocument.tags, path_literal)
        return or_(match, ~has_facet)

    async def get_relevant_lessons(
        self,
        project_id: UUID,
        symbol: str | None = None,
        limit: int = 5,
        source_type: str = "trade_lesson",
        *,
        direction: str | None = None,
        timeframe: str | None = None,
        outcome: str | None = None,
        market: str | None = None,
        workflow: str | None = None,
        strict: bool = False,
    ) -> list[dict]:
        """Retrieve the most recent lessons for a project, optionally scoped to facets.

        This is the canonical, lesson-scoped retrieval path used by the
        ``check_trade_lessons`` workflow step. It is strictly read-only and its result is
        consumed only as advisory prompt context — it never influences a deterministic
        safety gate.

        Args:
            project_id: Project scope (always enforced).
            symbol: e.g. "BTCUSDT" — matched against both the legacy bare symbol tag and
                the new ``symbol:<SYMBOL>`` tag. When ``None`` the symbol filter is skipped
                (project + source_type only), the safe fallback when no symbol resolves.
            limit: Maximum number of lessons to return.
            source_type: KnowledgeDocument ``source_type`` to filter on (default
                ``"trade_lesson"``). This is what makes ``source_type_filter`` effective.
            direction / timeframe / outcome / market / workflow: optional facet filters.
                In the default broad mode they never hide legacy lessons that lack the
                facet; the live pipeline passes none of them, preserving prior behaviour.
            strict: when True, every provided facet filter requires the matching
                namespaced tag (legacy/untagged lessons are excluded for that facet).

        Returns:
            List of dicts with keys: id, title, content, tags, created_at. Empty list when
            no lessons match — callers must treat this as a safe no-op, never an error.
        """
        conditions = [
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.source_type == source_type,
        ]
        if symbol:
            # Dual-match: legacy bare tag (``BTCUSDT``) OR new ``symbol:BTCUSDT`` tag,
            # tolerant of casing. PostgreSQL JSONB array containment: tags @> '["BTCUSDT"]'.
            sym_variants = {symbol, symbol.strip().upper()}
            symbol_ors = [KnowledgeDocument.tags.contains([s]) for s in sym_variants]
            symbol_ors += [KnowledgeDocument.tags.contains([f"symbol:{s}"]) for s in sym_variants]
            conditions.append(or_(*symbol_ors))

        facet_filters = (
            ("direction", _norm_direction(direction) if direction else None),
            ("timeframe", _norm_timeframe(timeframe) if timeframe else None),
            ("outcome", outcome.strip().lower() if outcome else None),
            ("market", _norm_market(market) if market else None),
            ("workflow", _norm_workflow(workflow) if workflow else None),
        )
        for facet, value in facet_filters:
            if value:
                conditions.append(self._facet_condition(facet, value, strict))

        stmt = (
            select(KnowledgeDocument)
            .where(and_(*conditions))
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        docs = list(result.scalars().all())

        return [
            {
                "id": str(doc.id),
                "title": doc.title,
                "content": doc.content,
                "tags": list(doc.tags or []),
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ]

    async def reflect_and_record(
        self,
        project_id: UUID,
        closed_trade: ClosedTrade,
    ) -> None:
        """Reflect on a just-closed trade and record a KB lesson (win OR loss).

        Invokes the already-seeded ``post_trade_review`` agent to produce an honest,
        structured analysis, writes the analysis back onto the TradeJournal reflection
        fields, and records a ``trade_lesson`` KnowledgeDocument so future runs retrieve
        it via the existing ``check_trade_lessons`` kb_search step.

        Best-effort: any failure is logged and swallowed so a trade run is never blocked.
        """
        journal = await self._db.get(TradeJournal, closed_trade.journal_id)
        if journal is None:
            logger.warning(
                "reflect_and_record: journal %s not found", closed_trade.journal_id
            )
            return

        agent = await self._resolve_reflection_agent(project_id)
        if agent is None:
            logger.warning(
                "reflect_and_record: no '%s' agent in project %s; recording raw lesson only",
                _REFLECTION_AGENT_ROLE,
                project_id,
            )
            review: dict = {}
        else:
            review = await self._run_reflection_agent(agent, journal, closed_trade)

        # ── Persist reflection back onto the journal ──
        what_worked = str(review.get("what_worked") or "").strip()
        what_failed = str(review.get("what_failed") or "").strip()
        mistakes = str(review.get("mistakes") or "").strip()
        learning_summary = str(review.get("learning_summary") or "").strip()
        suggestions = review.get("prompt_improvement_suggestions") or []

        if what_worked:
            journal.what_worked = what_worked
        if mistakes or what_failed:
            journal.mistakes = mistakes or what_failed
        improvement_parts: list[str] = []
        if learning_summary:
            improvement_parts.append(learning_summary)
        if isinstance(suggestions, list):
            for s in suggestions:
                if isinstance(s, dict):
                    improvement_parts.append(
                        f"[{s.get('agent', '?')}] {s.get('suggested_change', '')}".strip()
                    )
        if improvement_parts:
            journal.improvement = "\n".join(p for p in improvement_parts if p)
        if review:
            journal.post_review_md = json.dumps(review, ensure_ascii=False, indent=2)
        await self._db.flush()

        # ── Record the KB lesson for BOTH wins and losses ──
        error_summary = (
            what_failed
            or mistakes
            or learning_summary
            or f"Trade closed {closed_trade.result} at "
            f"{closed_trade.realized_pnl_pct if closed_trade.realized_pnl_pct is not None else 0.0:+.2f}%."
        )
        pattern = (
            str(review.get("thesis_rationale") or "").strip()
            or (journal.original_thesis or "Pattern not recorded")
        )
        await self.record_lesson(
            project_id=project_id,
            trade_id=closed_trade.position_id,
            error_summary=error_summary,
            symbol=closed_trade.symbol,
            pattern=pattern,
            agent_votes=journal.agent_votes or {},
            outcome=closed_trade.close_reason or closed_trade.result,
            pnl_pct=closed_trade.realized_pnl_pct
            if closed_trade.realized_pnl_pct is not None
            else 0.0,
            # direction is carried on the closed trade; market is grounded from env.
            # timeframe/workflow are not grounded on this close path → left unknown.
            direction=closed_trade.direction,
            market_type=_current_market_type(),
        )

        logger.info(
            "reflect_and_record: lesson stored for %s (%s, %.2f%%)",
            closed_trade.symbol,
            closed_trade.result,
            closed_trade.realized_pnl_pct or 0.0,
        )

    async def _resolve_reflection_agent(self, project_id: UUID):
        """Return the project's post_trade_review agent, or None."""
        agents, _ = await agent_config_repo.list_by_project(
            self._db, project_id=project_id, limit=100
        )
        for agent in agents:
            if (agent.role or "").strip() == _REFLECTION_AGENT_ROLE:
                return agent
        return None

    async def _run_reflection_agent(
        self, agent, journal: TradeJournal, closed_trade: ClosedTrade
    ) -> dict:
        """Invoke the reflection agent via the existing fallback runtime. Returns parsed JSON."""
        from app.services.model_fallback import run_with_fallback

        facts = {
            "symbol": closed_trade.symbol,
            "direction": closed_trade.direction,
            "result": closed_trade.result,
            "realized_pnl": closed_trade.realized_pnl,
            "realized_pnl_pct": closed_trade.realized_pnl_pct,
            "close_reason": closed_trade.close_reason,
            "entry_price": journal.entry_price,
            "exit_price": journal.exit_price,
            "holding_time_minutes": journal.holding_time_minutes,
            "original_thesis": journal.original_thesis,
            "agent_votes": journal.agent_votes or {},
            "what_happened": journal.what_happened,
        }
        prompt = (
            "A trade has closed. Analyse it honestly and return ONLY the JSON object your "
            "instructions specify — no other text. Base every claim strictly on these "
            "system-provided facts; do NOT invent data:\n"
            f"{json.dumps(facts, ensure_ascii=False, default=str)}"
        )
        system_prompt = agent.system_prompt or "You are the Post-Trade Review Agent."
        try:
            output, _meta = await run_with_fallback(
                agent, prompt=prompt, system_prompt=system_prompt, db=self._db
            )
        except Exception as exc:
            logger.warning("reflection agent run failed: %s", exc)
            return {}
        parsed = extract_json_object(output or "")
        return parsed if isinstance(parsed, dict) else {}

    async def trigger_post_trade_learning(
        self,
        project_id: UUID,
        run_id: UUID,
        pnl_pct: float,
    ) -> None:
        """Called after a trade closes.  Records a lesson only on a loss.

        Reads context from the run record to synthesise the lesson data.

        Args:
            project_id: Project scope.
            run_id: UUID of the completed run.
            pnl_pct: Realised P&L percentage.
        """
        if pnl_pct >= 0:
            # Only record lessons automatically for losing trades
            return

        run = await run_repo.get_run_by_id(self._db, run_id)
        if run is None:
            logger.warning(
                "trigger_post_trade_learning: run %s not found for project %s",
                run_id,
                project_id,
            )
            return

        # Extract context from the run's runtime summary and input payload
        runtime_summary: dict = run.runtime_summary or {}
        input_payload: dict = run.input_payload_json or {}

        symbol: str = runtime_summary.get("symbol") or input_payload.get("symbol") or "UNKNOWN"
        outcome: str = runtime_summary.get("trade_outcome") or input_payload.get("outcome") or "SL"
        pattern: str = (
            runtime_summary.get("market_pattern")
            or input_payload.get("pattern")
            or "Pattern not recorded"
        )
        agent_votes: dict = (
            runtime_summary.get("agent_votes") or input_payload.get("agent_votes") or {}
        )
        error_summary: str = (
            run.error_text
            or runtime_summary.get("error_summary")
            or f"Trade closed at {pnl_pct:+.2f}% P&L without a recorded error message."
        )

        # Direction is grounded only if the run actually recorded it — never fabricated.
        direction: str | None = (
            runtime_summary.get("direction")
            or input_payload.get("direction")
            or runtime_summary.get("side")
            or input_payload.get("side")
        )

        # Derive workflow kind + timeframe from the run's workflow name (grounded).
        workflow_name: str | None = None
        if run.workflow_id is not None:
            from app.db.models.workflow import Workflow

            workflow = await self._db.get(Workflow, run.workflow_id)
            workflow_name = workflow.name if workflow is not None else None
        workflow_kind, timeframe = _derive_workflow_timeframe(workflow_name)

        # Use a deterministic trade_id from the run id
        trade_id: UUID = UUID(str(run_id))

        await self.record_lesson(
            project_id=project_id,
            trade_id=trade_id,
            error_summary=error_summary,
            symbol=symbol,
            pattern=pattern,
            agent_votes=agent_votes,
            outcome=outcome,
            pnl_pct=pnl_pct,
            direction=direction,
            timeframe=timeframe,
            market_type=_current_market_type(),
            workflow=workflow_kind,
        )

        logger.info(
            "Post-trade lesson recorded for run %s, symbol=%s, pnl=%.2f%%",
            run_id,
            symbol,
            pnl_pct,
        )
