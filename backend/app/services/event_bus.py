"""In-memory event bus for real-time Control Room updates.

Agents emit events → WebSocket clients receive them via asyncio.Queue.
"""

import asyncio
import hashlib as _hashlib
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    type: str  # "task_started" | "agent_started" | "agent_chunk" | "agent_done" | "agent_error" | "task_done"
    project_id: str
    task: str = ""
    agent_name: str = ""
    agent_role: str = ""
    data: str = ""
    run_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EventBus:
    """Fan-out event bus: many publishers → many subscribers per project."""

    def __init__(self) -> None:
        # project_id → list of subscriber queues
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        # project_id → bounded recent history for replay on late subscribers
        self._history: dict[str, deque[AgentEvent]] = defaultdict(lambda: deque(maxlen=200))
        # Deduplication: key → last payload hash (only for run.step_output)
        self._last_event: dict[str, str] = {}

    def subscribe(self, project_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers[project_id].append(q)
        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue) -> None:
        import contextlib

        with contextlib.suppress(ValueError):
            self._subscribers[project_id].remove(q)

    def recent(self, project_id: str, limit: int = 100) -> list[AgentEvent]:
        history = self._history.get(project_id)
        if not history:
            return []
        return list(history)[-limit:]

    async def emit(self, event: AgentEvent) -> None:
        # Delta dedup: skip identical consecutive run.step_output events
        # to avoid flooding subscribers with repeated streaming output.
        if event.type == "run.step_output":
            key = f"{event.project_id}:{event.agent_name}:{event.type}"
            payload_hash = _hashlib.md5(str(event.data).encode()).hexdigest()[:8]
            if self._last_event.get(key) == payload_hash:
                return  # skip duplicate
            self._last_event[key] = payload_hash

        self._history[event.project_id].append(event)

        for q in list(self._subscribers.get(event.project_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("Control room queue full for project %s", event.project_id)


# Module-level singleton — shared across all requests in one process
event_bus = EventBus()
