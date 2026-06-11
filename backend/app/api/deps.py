"""API dependencies.

Dependency injection factories for services, repositories, and authentication.
"""
# ruff: noqa: I001, E402 - Imports structured for Jinja2 template conditionals

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.db.session import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession

DBSession = Annotated[AsyncSession, Depends(get_db_session)]
from fastapi import Request

from app.clients.redis import RedisClient


async def get_redis(request: Request) -> RedisClient:
    """Get Redis client from lifespan state."""
    return request.state.redis  # type: ignore[no-any-return]


Redis = Annotated[RedisClient, Depends(get_redis)]


# === Service Dependencies ===

from app.services.user import UserService
from app.services.conversation import ConversationService


def get_user_service(db: DBSession) -> UserService:
    """Create UserService instance with database session."""
    return UserService(db)


UserSvc = Annotated[UserService, Depends(get_user_service)]


def get_conversation_service(db: DBSession) -> ConversationService:
    """Create ConversationService instance with database session."""
    return ConversationService(db)


ConversationSvc = Annotated[ConversationService, Depends(get_conversation_service)]

from app.services.conversation_share import ConversationShareService
def get_conversation_share_service(db: DBSession) -> ConversationShareService:
    """Create ConversationShareService instance with database session."""
    return ConversationShareService(db)


ConversationShareSvc = Annotated[ConversationShareService, Depends(get_conversation_share_service)]

# Message rating service
from app.services.message_rating import MessageRatingService


def get_rating_service(db: DBSession) -> MessageRatingService:
    """Create MessageRatingService instance with database session."""
    return MessageRatingService(db)


MessageRatingSvc = Annotated[MessageRatingService, Depends(get_rating_service)]
from app.services.file_upload import FileUploadService


def get_file_upload_service(db: DBSession) -> FileUploadService:
    """Create FileUploadService instance with database session."""
    return FileUploadService(db)


FileUploadSvc = Annotated[FileUploadService, Depends(get_file_upload_service)]
# === Authentication Dependencies ===

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    user_service: UserSvc,
) -> User:
    """Get current authenticated user from JWT token.

    Returns the full User object including role information.

    Raises:
        AuthenticationError: If token is invalid or user not found.
    """
    from uuid import UUID

    from app.core.security import verify_token

    payload = verify_token(token)
    if payload is None:
        raise AuthenticationError(message="Invalid or expired token")

    # Ensure this is an access token, not a refresh token
    if payload.get("type") != "access":
        raise AuthenticationError(message="Invalid token type")

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError(message="Invalid token payload")

    user = await user_service.get_by_id(UUID(user_id))
    if not user.is_active:
        raise AuthenticationError(message="User account is disabled")

    return user


class RoleChecker:
    """Dependency class for role-based access control.

    Usage:
        # Require admin role
        @router.get("/admin-only")
        async def admin_endpoint(
            user: Annotated[User, Depends(RoleChecker(UserRole.ADMIN))]
        ):
            ...

        # Require any authenticated user
        @router.get("/users")
        async def users_endpoint(
            user: Annotated[User, Depends(get_current_user)]
        ):
            ...
    """

    def __init__(self, required_role: UserRole) -> None:
        self.required_role = required_role

    async def __call__(
        self,
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        """Check if user has the required role.

        Raises:
            AuthorizationError: If user doesn't have the required role.
        """
        if not user.has_role(self.required_role):
            raise AuthorizationError(
                message=f"Role '{self.required_role.value}' required for this action"
            )
        return user


async def get_current_active_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current user and verify they are a superuser.

    Raises:
        AuthorizationError: If user is not a superuser.
    """
    if not current_user.has_role(UserRole.ADMIN):
        raise AuthorizationError(message="Admin privileges required")
    return current_user


# Type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]
CurrentAdmin = Annotated[User, Depends(RoleChecker(UserRole.ADMIN))]


# is_app_admin is a global flag on the User model — independent of team
# membership. Routes guarded by this dep (e.g. /admin/users) stay reachable
# even when teams are disabled, so the dep itself must not be gated.
async def _require_app_admin(user: CurrentUser) -> "User":  # type: ignore[name-defined]
    """Raises 403 unless the user has the is_app_admin flag set."""
    if not getattr(user, "is_app_admin", False):
        raise AuthorizationError(message="App admin privileges required")
    return user


CurrentAppAdmin = Annotated["User", Depends(_require_app_admin)]  # type: ignore[valid-type]


# WebSocket authentication dependency
from fastapi import WebSocket, Cookie


_WS_TOKEN_PROTOCOL_PREFIX = "access_token."


def _extract_ws_auth(websocket: WebSocket) -> tuple[str | None, str | None]:
    """Parse Sec-WebSocket-Protocol header for an auth token + app subprotocol.

    Clients pass the token as a subprotocol of the form
    ``access_token.<JWT>`` alongside an optional application subprotocol
    (e.g. ``chat``). Returns (token, app_subprotocol) — either may be None.
    """
    raw = websocket.headers.get("sec-websocket-protocol") or ""
    token: str | None = None
    app_subprotocol: str | None = None
    for proto in (p.strip() for p in raw.split(",") if p.strip()):
        if proto.startswith(_WS_TOKEN_PROTOCOL_PREFIX):
            token = proto[len(_WS_TOKEN_PROTOCOL_PREFIX):]
        elif app_subprotocol is None:
            app_subprotocol = proto
    return token, app_subprotocol


async def get_current_user_ws(
    websocket: WebSocket,
    access_token: str | None = Cookie(None),
) -> User:
    """Authenticate a WebSocket connection.

    Token sources, checked in order:
    1. ``Sec-WebSocket-Protocol`` header, in the form ``access_token.<JWT>``.
       The chosen application subprotocol (e.g. ``chat``) is echoed back on
       ``accept()`` via ``websocket.state.accept_subprotocol``.
    2. Same-origin ``access_token`` cookie (fallback for same-origin clients).

    Tokens in query strings are NOT accepted — they leak into logs and
    Referer headers.

    Raises:
        AuthenticationError: If token is invalid or user not found.
    """
    from uuid import UUID

    from app.core.security import verify_token

    subprotocol_token, app_subprotocol = _extract_ws_auth(websocket)
    websocket.state.accept_subprotocol = app_subprotocol

    auth_token = subprotocol_token or access_token

    if not auth_token:
        await websocket.close(code=4001, reason="Missing authentication token")
        raise AuthenticationError(message="Missing authentication token")

    payload = verify_token(auth_token)
    if payload is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        raise AuthenticationError(message="Invalid or expired token")

    if payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token type")
        raise AuthenticationError(message="Invalid token type")

    user_id = payload.get("sub")
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid token payload")
        raise AuthenticationError(message="Invalid token payload")

    from app.db.session import get_db_context

    async with get_db_context() as db:
        user_service = UserService(db)
        user = await user_service.get_by_id(UUID(user_id))

        if not user.is_active:
            await websocket.close(code=4001, reason="User account is disabled")
            raise AuthenticationError(message="User account is disabled")

        # Eagerly load all columns, then detach from session to avoid
        # "instance not bound to a Session" errors after the context manager exits
        await db.refresh(user)
        db.expunge(user)
        return user

import secrets

from fastapi.security import APIKeyHeader

from app.core.exceptions import AuthenticationError, AuthorizationError

api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)


async def verify_api_key(
    api_key: Annotated[str | None, Depends(api_key_header)],
) -> str:
    """Verify API key from header.

    Uses constant-time comparison to prevent timing attacks.

    Raises:
        AuthenticationError: If API key is missing.
        AuthorizationError: If API key is invalid.
    """
    if api_key is None:
        raise AuthenticationError(message="API Key header missing")
    if not secrets.compare_digest(api_key, settings.API_KEY):
        raise AuthorizationError(message="Invalid API Key")
    return api_key


ValidAPIKey = Annotated[str, Depends(verify_api_key)]
from app.services.user_slash_command import UserSlashCommandService


def get_user_slash_command_service(db: DBSession) -> UserSlashCommandService:
    return UserSlashCommandService(db)


UserSlashCommandSvc = Annotated[
    UserSlashCommandService, Depends(get_user_slash_command_service)
]
from app.services.admin import AdminService
def get_admin_service(db: DBSession) -> AdminService:
    """Create AdminService instance — used by admin REST routes (always
    available, independent of the optional SQLAdmin UI)."""
    return AdminService(db)


AdminSvc = Annotated[AdminService, Depends(get_admin_service)]

from app.services.project import ProjectService
from app.services.agent_config import AgentConfigService
from app.services.knowledge import KnowledgeService


def get_project_service(db: DBSession) -> ProjectService:
    return ProjectService(db)


def get_agent_config_service(db: DBSession) -> AgentConfigService:
    return AgentConfigService(db)


def get_knowledge_service(db: DBSession) -> KnowledgeService:
    return KnowledgeService(db)


ProjectSvc = Annotated[ProjectService, Depends(get_project_service)]
AgentConfigSvc = Annotated[AgentConfigService, Depends(get_agent_config_service)]
KnowledgeSvc = Annotated[KnowledgeService, Depends(get_knowledge_service)]

from app.services.app_setting import AppSettingService


def get_app_setting_service(db: DBSession) -> AppSettingService:
    return AppSettingService(db)


AppSettingSvc = Annotated[AppSettingService, Depends(get_app_setting_service)]

from app.services.agent_chat import AgentChatService


def get_agent_chat_service(db: DBSession) -> AgentChatService:
    return AgentChatService(db)


AgentChatSvc = Annotated[AgentChatService, Depends(get_agent_chat_service)]

from app.services.workflow import WorkflowService, ScheduleService
from app.services.run import RunService
from app.services.run_executor import RunExecutor
from app.services.room import RoomService


def get_workflow_service(db: DBSession) -> WorkflowService:
    return WorkflowService(db)


def get_schedule_service(db: DBSession) -> ScheduleService:
    return ScheduleService(db)


def get_run_service(db: DBSession) -> RunService:
    return RunService(db)


def get_run_executor(db: DBSession) -> RunExecutor:
    return RunExecutor(db)


def get_room_service(db: DBSession) -> RoomService:
    return RoomService(db)


WorkflowSvc = Annotated[WorkflowService, Depends(get_workflow_service)]
ScheduleSvc = Annotated[ScheduleService, Depends(get_schedule_service)]
RunSvc = Annotated[RunService, Depends(get_run_service)]
RunExecutorSvc = Annotated[RunExecutor, Depends(get_run_executor)]
RoomSvc = Annotated[RoomService, Depends(get_room_service)]

from app.services.handoff import HandoffService


def get_handoff_service(db: DBSession) -> HandoffService:
    return HandoffService(db)


HandoffSvc = Annotated[HandoffService, Depends(get_handoff_service)]

from app.services.secret import SecretService
from app.services.integration import IntegrationService


def get_secret_service(db: DBSession) -> SecretService:
    return SecretService(db)


def get_integration_service(db: DBSession) -> IntegrationService:
    return IntegrationService(db)


SecretSvc = Annotated[SecretService, Depends(get_secret_service)]
IntegrationSvc = Annotated[IntegrationService, Depends(get_integration_service)]

# === Project RBAC + Isolation ===

from app.core.rbac import Permission, ProjectAccess


def require_project_permission(permission: Permission):
    """FastAPI dependency factory enforcing a project-scoped permission.

    Resolves the caller's role within the ``{project_id}`` path parameter and
    raises 403 if ``permission`` is absent (404 if the project is not visible to
    the caller). Returns the resolved :class:`ProjectAccess` so the handler can
    reuse ``access.project`` without a second query.

    Usage::

        @router.post("/projects/{project_id}/runs/{run_id}/approve")
        async def approve(
            access: Annotated[ProjectAccess, Depends(require_project_permission(Permission.TRADE_APPROVE))],
        ):
            ...

    Most existing routes call ``project_svc.resolve_access(..., require=...)``
    directly; this dependency is the preferred pattern for new routes and
    WebSocket handlers.
    """

    async def _dependency(
        project_id: UUID,
        user: CurrentUser,
        project_svc: ProjectSvc,
    ) -> ProjectAccess:
        return await project_svc.resolve_access(project_id, user, require=permission)

    return _dependency
