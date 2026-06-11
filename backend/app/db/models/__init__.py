"""Database models."""
# ruff: noqa: I001, RUF022 - Imports structured for Jinja2 template conditionals
from app.db.models.user import User
from app.db.models.conversation import Conversation, Message, ToolCall
from app.db.models.chat_file import ChatFile
from app.db.models.message_rating import MessageRating
from app.db.models.conversation_share import ConversationShare
from app.db.models.user_slash_command import UserSlashCommand
from app.db.models.project import Project, AgentConfig, KnowledgeDocument
from app.db.models.project_member import ProjectMember
from app.db.models.app_setting import AppSetting
from app.db.models.workflow import (
    Workflow, Schedule, Run, RunStep, RunMetric, PromptRegistryEntry, TraceEvent,
)
from app.db.models.room import Room, RoomMessage
from app.db.models.handoff import Handoff
from app.db.models.secret import Secret
from app.db.models.integration import Integration
from app.db.models.agent_template import AgentTemplate
from app.db.models.skill import Skill
from app.db.models.knowledge_template import KnowledgeTemplate
from app.db.models.cost_tracking import CostEvent, CostBudget
from app.db.models.notification_config import NotificationConfig
from app.db.models.trigger import Trigger
from app.db.models.skill_version import SkillVersion
from app.db.models.context_compaction import ContextCompaction
from app.db.models.crypto_trading import (
    NewsEvent, MarketSnapshot, TokenCandidate, AgentVote, TradeProposal,
    TradeExecution, Position, TradeJournal,
)

__all__ = [
    'User', 'Conversation', 'Message', 'ToolCall', 'ChatFile', 'MessageRating',
    'ConversationShare', 'UserSlashCommand', 'Project', 'AgentConfig', 'KnowledgeDocument',
    'ProjectMember',
    'AppSetting', 'Workflow', 'Schedule', 'Run', 'RunStep', 'RunMetric',
    'PromptRegistryEntry', 'TraceEvent', 'Room', 'RoomMessage', 'Handoff',
    'Secret', 'Integration', 'AgentTemplate', 'Skill', 'KnowledgeTemplate',
    'CostEvent', 'CostBudget', 'NotificationConfig', 'Trigger', 'SkillVersion',
    'ContextCompaction', 'NewsEvent', 'MarketSnapshot', 'TokenCandidate',
    'AgentVote', 'TradeProposal', 'TradeExecution', 'Position', 'TradeJournal',
]
