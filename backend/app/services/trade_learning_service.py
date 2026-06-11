"""Trade Learning Service — stores trade mistakes as KB entries and retrieves
them before new trades to prevent repeating errors."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.project_paths import project_vault_dir
from app.db.models.project import KnowledgeDocument
from app.repositories import knowledge_repo, run_repo

logger = logging.getLogger(__name__)


def _build_lesson_content(
    trade_id: UUID,
    symbol: str,
    pattern: str,
    agent_votes: dict,
    outcome: str,
    pnl_pct: float,
    error_summary: str,
) -> str:
    """Build a structured Markdown document for a trade lesson."""
    pnl_label = f"{pnl_pct:+.2f}%"
    vote_lines = "\n".join(
        f"  - **{agent}**: {vote}" for agent, vote in agent_votes.items()
    ) if agent_votes else "  - (no agent votes recorded)"

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
    ) -> None:
        """Persist a trade lesson as a KnowledgeDocument and a vault .md file.

        Args:
            project_id: Project owning the trade.
            trade_id: UUID of the trade record for cross-reference.
            error_summary: Human-readable description of what went wrong (or right).
            symbol: e.g. "BTCUSDT".
            pattern: Short description of the market pattern at entry.
            agent_votes: Dict of {agent_name: "BUY"|"SELL"|"HOLD"}.
            outcome: e.g. "TP", "SL", "MANUAL_CLOSE".
            pnl_pct: Realised P&L percentage (negative = loss).
        """
        tags: list[str] = [
            "trade_lesson",
            symbol,
            "loss" if pnl_pct < 0 else "win",
        ]
        title = f"Trade Lesson: {symbol} {outcome}"
        content = _build_lesson_content(
            trade_id=trade_id,
            symbol=symbol,
            pattern=pattern,
            agent_votes=agent_votes,
            outcome=outcome,
            pnl_pct=pnl_pct,
            error_summary=error_summary,
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

    async def get_relevant_lessons(
        self,
        project_id: UUID,
        symbol: str,
        limit: int = 5,
    ) -> list[dict]:
        """Retrieve the most recent trade lessons for a given symbol.

        Args:
            project_id: Project scope.
            symbol: e.g. "BTCUSDT" — must match a tag on the document.
            limit: Maximum number of lessons to return.

        Returns:
            List of dicts with keys: title, content, created_at.
        """
        stmt = (
            select(KnowledgeDocument)
            .where(
                and_(
                    KnowledgeDocument.project_id == project_id,
                    KnowledgeDocument.source_type == "trade_lesson",
                    # PostgreSQL JSONB array containment: tags @> '["BTCUSDT"]'
                    KnowledgeDocument.tags.contains([symbol]),
                )
            )
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        docs = list(result.scalars().all())

        return [
            {
                "title": doc.title,
                "content": doc.content,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ]

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

        symbol: str = (
            runtime_summary.get("symbol")
            or input_payload.get("symbol")
            or "UNKNOWN"
        )
        outcome: str = (
            runtime_summary.get("trade_outcome")
            or input_payload.get("outcome")
            or "SL"
        )
        pattern: str = (
            runtime_summary.get("market_pattern")
            or input_payload.get("pattern")
            or "Pattern not recorded"
        )
        agent_votes: dict = (
            runtime_summary.get("agent_votes")
            or input_payload.get("agent_votes")
            or {}
        )
        error_summary: str = (
            run.error_text
            or runtime_summary.get("error_summary")
            or f"Trade closed at {pnl_pct:+.2f}% P&L without a recorded error message."
        )

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
        )

        logger.info(
            "Post-trade lesson recorded for run %s, symbol=%s, pnl=%.2f%%",
            run_id,
            symbol,
            pnl_pct,
        )
