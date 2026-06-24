"""AgentConfig schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema

ToolPermission = Literal[
    "web_search", "code_exec", "file_read", "file_write", "api_call", "db_query"
]
MemoryType = Literal["none", "short_term", "long_term"]


class AgentConfigCreate(BaseSchema):
    name: str = Field(max_length=255)
    role: str = Field(max_length=100)
    system_prompt: str
    tools_config: dict = Field(default_factory=dict)
    order_index: int = Field(default=0)
    # ── appearance / runtime ──
    avatar: str = Field(default="bot", max_length=120)
    runtime_kind: str = Field(default="anthropic-api", max_length=32)
    model: str = Field(default="", max_length=120)
    working_directory: str = Field(default="")
    # ── skills / tuning ──
    tool_permissions: list[ToolPermission] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    max_tokens: int = Field(default=2048, ge=1, le=200000)
    temperature: int = Field(default=70, ge=0, le=200)  # ×100
    memory_type: MemoryType = "none"
    context_window_size: int = Field(default=10, ge=0, le=100)


class AgentConfigUpdate(BaseSchema):
    name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=100)
    system_prompt: str | None = None
    tools_config: dict | None = None
    is_active: bool | None = None
    order_index: int | None = None
    avatar: str | None = Field(default=None, max_length=120)
    runtime_kind: str | None = Field(default=None, max_length=32)
    model: str | None = Field(default=None, max_length=120)
    working_directory: str | None = None
    tool_permissions: list[ToolPermission] | None = None
    skill_ids: list[str] | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=200000)
    temperature: int | None = Field(default=None, ge=0, le=200)
    memory_type: MemoryType | None = None
    context_window_size: int | None = Field(default=None, ge=0, le=100)


class AgentConfigRead(BaseSchema):
    id: UUID
    project_id: UUID
    name: str
    role: str
    system_prompt: str
    tools_config: dict
    is_active: bool
    order_index: int
    avatar: str
    runtime_kind: str
    model: str
    working_directory: str
    tool_permissions: list[str]
    skill_ids: list[str]
    max_tokens: int
    temperature: int
    memory_type: str
    context_window_size: int
    created_at: datetime
    updated_at: datetime | None


class AgentConfigList(BaseSchema):
    items: list[AgentConfigRead]
    total: int
