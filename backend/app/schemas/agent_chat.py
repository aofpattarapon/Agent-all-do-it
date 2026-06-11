"""Agent direct-chat schemas."""

from pydantic import Field

from app.schemas.base import BaseSchema


class AgentChatRequest(BaseSchema):
    message: str = Field(min_length=1, max_length=10000)
    include_knowledge: bool = True


class AgentChatResponse(BaseSchema):
    response: str
    agent_name: str
    agent_role: str
    tokens_used: int | None = None
