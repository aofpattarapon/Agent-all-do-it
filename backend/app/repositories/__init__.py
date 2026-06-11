"""Repository layer for database operations."""
# ruff: noqa: I001, RUF022 - Imports structured for Jinja2 template conditionals

from app.repositories import user as user_repo

from app.repositories import conversation as conversation_repo

from app.repositories import chat_file as chat_file_repo

from app.repositories import conversation_share as conversation_share_repo
from app.repositories import message_rating as message_rating_repo

from app.repositories import user_slash_command as user_slash_command_repo
from app.repositories import project as project_repo
from app.repositories import project_member as project_member_repo
from app.repositories import agent_config as agent_config_repo
from app.repositories import knowledge as knowledge_repo
from app.repositories import app_setting as app_setting_repo
from app.repositories import workflow as workflow_repo
from app.repositories import run as run_repo
from app.repositories import room as room_repo
from app.repositories import handoff as handoff_repo
from app.repositories import secret as secret_repo
from app.repositories import integration as integration_repo
from app.repositories import agent_template as agent_template_repo
from app.repositories import context_compaction as context_compaction_repo

# schedule and room_message are sub-namespaces within their parent modules;
# expose them as aliases for convenience in service imports
from app.repositories.workflow import (
    get_schedule_by_id,
    list_schedules_by_workflow,
    create_schedule,
    update_schedule,
    delete_schedule,
)
from app.repositories.run import (
    get_run_step_by_id,
    list_steps_by_run,
    create_run_step,
    update_run_step,
    get_run_metric_by_run,
    upsert_run_metric,
)
from app.repositories.room import (
    list_messages_by_room,
    create_room_message,
)

# Convenience module-level aliases expected by services
schedule_repo = workflow_repo
run_step_repo = run_repo
room_message_repo = room_repo

__all__ = [
    "user_repo",
    "conversation_repo",
    "chat_file_repo",
    "conversation_share_repo",
    "message_rating_repo",
    "user_slash_command_repo",
    "project_repo",
    "project_member_repo",
    "agent_config_repo",
    "knowledge_repo",
    "app_setting_repo",
    "workflow_repo",
    "schedule_repo",
    "run_repo",
    "run_step_repo",
    "room_repo",
    "room_message_repo",
    "handoff_repo",
    "secret_repo",
    "integration_repo",
    "agent_template_repo",
    "context_compaction_repo",
]
