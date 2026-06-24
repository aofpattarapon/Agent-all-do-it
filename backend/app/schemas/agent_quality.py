"""Read-only agent quality schemas (Phase F)."""

from datetime import datetime
from uuid import UUID

from app.schemas.base import BaseSchema


class AgentQualityRead(BaseSchema):
    """Per-agent quality metrics derived from runs, run_steps, handoffs, and votes."""

    agent_id: UUID
    name: str
    role: str
    is_active: bool
    total_steps: int
    total_runs: int
    successful_outputs: int
    failed_outputs: int
    validation_failures: int
    contract_failures: int
    retry_count: int
    error_runs: int
    last_activity: datetime | None
    quality_rate: float


class AgentQualityList(BaseSchema):
    """Aggregated quality dashboard payload."""

    items: list[AgentQualityRead]
    generated_at: datetime
