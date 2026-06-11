"""TraceEmitter service (ported from SDLC TraceEmitter).

Appends span-style :class:`TraceEvent` rows. The RunExecutor creates one
``trace_id`` per run and emits ``run.started`` / ``step.started`` /
``step.completed`` / ``run.completed`` spans under it.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow import TraceEvent


class TraceEmitter:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def emit(
        self,
        *,
        event_type: str,
        project_id: UUID | None = None,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
        parent_span_id: UUID | None = None,
        summary: str = "",
        event_status: str = "",
        payload: dict | None = None,
    ) -> TraceEvent:
        """Insert and return a new :class:`TraceEvent` row.

        Generates a fresh ``span_id`` automatically (model default). When
        ``trace_id`` is omitted the row's ``span_id`` doubles as a root trace —
        callers should normally pass the run's shared ``trace_id``.
        """
        event = TraceEvent(
            event_type=event_type,
            project_id=project_id,
            run_id=run_id,
            trace_id=trace_id or run_id or UUID(int=0),
            parent_span_id=parent_span_id,
            summary=summary[:5000] if summary else "",
            event_status=event_status,
            payload_json=payload or {},
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event
