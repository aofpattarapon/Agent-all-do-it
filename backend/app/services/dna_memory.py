"""Scored knowledge retrieval service (ported from SDLC DNAMemory).

Ranks ``KnowledgeDocument`` rows by confidence score plus simple text
relevance, increments their use count when returned, and adjusts confidence
based on downstream outcomes (approved/rejected, etc.).
"""

import logging
import re
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import KnowledgeDocument
from app.repositories import knowledge_repo

logger = logging.getLogger(__name__)

# Outcome classification.
_POSITIVE_OUTCOMES = {"approved", "quality_passed"}
_NEGATIVE_OUTCOMES = {"rejected", "revision_requested"}

_POSITIVE_DELTA = 10
_NEGATIVE_DELTA = -15
_MIN_SCORE = 0
_MAX_SCORE = 100

_TERM_RE = re.compile(r"[a-zA-Z0-9]+")


def _clamp(value: int) -> int:
    return max(_MIN_SCORE, min(_MAX_SCORE, value))


def _terms(query: str) -> list[str]:
    return [t for t in _TERM_RE.findall(query or "") if len(t) >= 2]


class DNAMemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_relevant(
        self,
        project_id: UUID,
        query: str,
        *,
        role: str | None = None,
        max_entries: int = 4,
        min_confidence: int = 30,
    ) -> list[KnowledgeDocument]:
        """Return the most relevant, confident knowledge docs for a query.

        Ranks by confidence_score desc, breaking ties by use_count desc. When
        the query contains terms, restricts to docs whose title/content match
        at least one term (case-insensitive). Increments use_count on the
        returned docs.
        """
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.confidence_score >= min_confidence,
        )

        terms = _terms(query)
        if terms:
            conditions = []
            for term in terms:
                like = f"%{term}%"
                conditions.append(KnowledgeDocument.title.ilike(like))
                conditions.append(KnowledgeDocument.content.ilike(like))
            stmt = stmt.where(or_(*conditions))

        stmt = stmt.order_by(
            KnowledgeDocument.confidence_score.desc(),
            KnowledgeDocument.use_count.desc(),
            KnowledgeDocument.created_at.desc(),
        ).limit(max_entries)

        result = await self.db.execute(stmt)
        docs = list(result.scalars().all())

        for doc in docs:
            doc.use_count += 1
        if docs:
            await self.db.flush()

        return docs

    async def record_outcome(self, doc_id: UUID, outcome: str) -> KnowledgeDocument | None:
        """Adjust a doc's confidence based on a downstream outcome.

        Positive outcomes promote the score (+10) and bump positive_count;
        negative outcomes demote it (-15) and bump negative_count. The score is
        clamped to [0, 100]. Unknown outcomes are a no-op.
        """
        doc = await knowledge_repo.get_by_id(self.db, doc_id)
        if doc is None:
            return None

        normalized = (outcome or "").strip().lower()
        if normalized in _POSITIVE_OUTCOMES:
            doc.positive_count += 1
            doc.confidence_score = _clamp(doc.confidence_score + _POSITIVE_DELTA)
        elif normalized in _NEGATIVE_OUTCOMES:
            doc.negative_count += 1
            doc.confidence_score = _clamp(doc.confidence_score + _NEGATIVE_DELTA)
        else:
            logger.debug("record_outcome ignoring unknown outcome %r", outcome)
            return doc

        await self.db.flush()
        await self.db.refresh(doc)
        return doc
