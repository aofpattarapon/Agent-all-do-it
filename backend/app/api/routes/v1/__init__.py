"""API v1 router aggregation."""
# ruff: noqa: I001 - Imports structured for Jinja2 template conditionals

from fastapi import APIRouter

from app.api.routes.v1 import health
from app.api.routes.v1 import admin_users, auth, users
from app.api.routes.v1 import admin_ratings
from app.api.routes.v1 import conversations
from app.api.routes.v1 import admin_conversations
from app.api.routes.v1 import agent
from app.api.routes.v1 import files
from app.api.routes.v1 import me_slash_commands
from app.api.routes.v1 import admin_stats
from app.api.routes.v1 import projects, knowledge, supervisor, app_settings, control_room
from app.api.routes.v1 import workflows, runs, rooms, webhooks
from app.api.routes.v1 import admin_agents
from app.api.routes.v1 import handoffs
from app.api.routes.v1 import secrets
from app.api.routes.v1 import integrations
from app.api.routes.v1 import dashboard
from app.api.routes.v1 import agent_templates
from app.api.routes.v1 import knowledge_templates
from app.api.routes.v1 import skills
from app.api.routes.v1 import cost
from app.api.routes.v1 import context_compactions
from app.api.routes.v1 import skill_versions
from app.api.routes.v1 import trading
from app.api.routes.v1 import backtest
from app.api.routes.v1 import admin, admin_setup

v1_router = APIRouter()

# Health check routes (no auth required)
v1_router.include_router(health.router, tags=["health"])

# Authentication routes
v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# User routes
v1_router.include_router(users.router, prefix="/users", tags=["users"])

# Admin: message-rating analytics
v1_router.include_router(admin_ratings.router, prefix="/admin/ratings", tags=["admin:ratings"])

# Conversation routes (AI chat persistence)
v1_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])

# AI Agent routes
v1_router.include_router(agent.router, tags=["agent"])

# File upload/download routes
v1_router.include_router(files.router, tags=["files"])

# Admin: conversation browser
v1_router.include_router(
    admin_conversations.router, prefix="/admin/conversations", tags=["admin-conversations"]
)

# Admin: user management + impersonation
v1_router.include_router(admin_users.router, prefix="/admin/users", tags=["admin:users"])
v1_router.include_router(
    me_slash_commands.router, prefix="/me/slash-commands", tags=["me:slash-commands"]
)
v1_router.include_router(admin_stats.router, prefix="/admin", tags=["admin:stats"])
v1_router.include_router(admin_setup.router, prefix="/admin", tags=["admin:setup"])
v1_router.include_router(admin.router, prefix="/admin", tags=["admin:seed"])

# Projects, Agents, Knowledge, Supervisor
v1_router.include_router(projects.router, tags=["projects"])
v1_router.include_router(knowledge.router, tags=["knowledge"])
v1_router.include_router(supervisor.router, tags=["supervisor"])
v1_router.include_router(app_settings.router, prefix="/admin", tags=["admin:settings"])
v1_router.include_router(control_room.router, tags=["control-room"])

# Workflows, Runs, Rooms, Webhooks
v1_router.include_router(workflows.router, tags=["workflows"])
v1_router.include_router(runs.router, tags=["runs"])
v1_router.include_router(rooms.router, tags=["rooms"])
v1_router.include_router(webhooks.router, tags=["webhooks"])
v1_router.include_router(admin_agents.router, prefix="/admin", tags=["admin:agents-workflows"])
v1_router.include_router(handoffs.router, tags=["handoffs"])
v1_router.include_router(secrets.router, tags=["secrets"])
v1_router.include_router(integrations.router, tags=["integrations"])
v1_router.include_router(dashboard.router, tags=["dashboard"])
v1_router.include_router(agent_templates.router, tags=["agent-templates"])
v1_router.include_router(knowledge_templates.router, tags=["knowledge-templates"])
v1_router.include_router(skills.router, tags=["skills"])
v1_router.include_router(cost.router, tags=["cost"])
v1_router.include_router(context_compactions.router, tags=["context-compactions"])
v1_router.include_router(skill_versions.router, tags=["skill-versions"])
v1_router.include_router(trading.router, tags=["trading"])
v1_router.include_router(backtest.router, tags=["backtest"])
