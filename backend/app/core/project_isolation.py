"""Project data-isolation enforcement.

The hub's core promise is *shared config, isolated data*: an agent or user
operating in Project A must never read Project B's rows. Ownership is checked at
the HTTP boundary (see ``app.services.project.ProjectService.resolve_access``),
but agent **tools** talk to the database directly, so they need their own
enforcement layer. The biggest hole today is the ``db_query`` agent tool, which
otherwise runs arbitrary ``SELECT`` over the whole database.

This module provides three things, all standard-library only so they can be
unit-tested without a database:

1. :func:`build_scoped_query` — the *preferred* structured query path. The
   caller names a table and optional column filters; we emit fully
   parameterised SQL with a mandatory ``project_id = :project_id`` predicate.
   Injection-proof by construction.
2. :func:`validate_raw_query` — a defense-in-depth guard for free-form
   ``SELECT`` strings. It enforces read-only single statements and *requires*
   an explicit project predicate for any project-scoped table. This is a guard,
   not a parser-grade guarantee; for a hard guarantee enable Postgres RLS (see
   ``PHASE_0_NOTES``).
3. :class:`ProjectIsolationMiddleware` — a tiny ASGI middleware that pins the
   ``project_id`` from the request path onto ``request.state`` for downstream
   logging / auditing / guard context.
"""

from __future__ import annotations

import re
from typing import Any

# ── Table classification ────────────────────────────────────────────────────
#
# DEFAULT-DENY: a table an agent may read must be explicitly listed below. Any
# table not classified here is rejected by the raw-query guard.

#: Tables that carry a ``project_id`` column and MUST be filtered by it.
PROJECT_SCOPED_TABLES: frozenset[str] = frozenset(
    {
        "agent_configs",
        "knowledge_documents",
        "workflows",
        "schedules",
        "runs",
        "run_steps",
        "run_metrics",
        "trace_events",
        "handoffs",
        "rooms",
        "room_messages",
        "secrets",
        "integrations",
    }
)

#: The projects table is scoped on its *primary key* rather than ``project_id``.
PROJECT_ROOT_TABLE = "projects"

#: Globally-shared, read-only catalogs — safe to read unscoped (shared config).
GLOBAL_READONLY_TABLES: frozenset[str] = frozenset(
    {
        "agent_templates",
        "skills",
        "knowledge_templates",
        "app_settings",
    }
)

#: Columns that may appear in a structured filter value position are bound as
#: parameters, so only the *identifier* needs validation.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLE_REF_RE = re.compile(r"\b(?:from|join)\s+([A-Za-z_][\w.\"]*)", re.IGNORECASE)

#: Write / DDL / side-effecting keywords forbidden anywhere in a raw query.
_FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "truncate",
    "grant",
    "revoke",
    "attach",
    "detach",
    "copy",
    "into",
    "vacuum",
    "analyze",
    "call",
    "do",
    "merge",
    "replace",
    "set",
    "begin",
    "commit",
    "rollback",
    "execute",
    "prepare",
    "lock",
    "reindex",
    "cluster",
    "comment",
    "refresh",
)

#: Dangerous functions / extensions that can exfiltrate or side-effect.
_FORBIDDEN_FUNCTIONS: tuple[str, ...] = (
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "lo_import",
    "lo_export",
    "dblink",
    "current_setting",
    "set_config",
    "pg_terminate",
    "pg_cancel",
    "pg_stat_file",
)

#: Cheap tautology patterns to catch the most common ``OR 1=1`` style bypass in
#: raw mode. Structured mode is the real safety guarantee.
_TAUTOLOGY_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bor\b\s+\d+\s*=\s*\d+", re.IGNORECASE),
    re.compile(r"\bor\b\s+'[^']*'\s*=\s*'[^']*'", re.IGNORECASE),
    re.compile(r"\bor\b\s+true\b", re.IGNORECASE),
    re.compile(r"\bor\b\s+\d+\b(?!\s*=)", re.IGNORECASE),
)

_MAX_QUERY_ROWS = 100


class QueryIsolationError(ValueError):
    """Raised when a query violates project-isolation or read-only rules."""


def _normalize_table(raw: str) -> str:
    """Strip schema qualifier and quotes from a captured table reference."""
    name = raw.strip().strip('"')
    if "." in name:
        name = name.split(".")[-1]
    return name.strip('"').lower()


def _referenced_tables(sql: str) -> set[str]:
    return {_normalize_table(m.group(1)) for m in _TABLE_REF_RE.finditer(sql)}


def _has_project_predicate(sql: str, column: str, project_id: str) -> bool:
    """True if ``sql`` contains ``<column> = '<project_id>'`` or ``= :project_id``.

    Allows an optional table alias/qualifier (``r.project_id = ...``) and either
    a single-quoted literal matching ``project_id`` exactly, or the named bind
    parameter ``:project_id``.
    """
    col = re.escape(column)
    pid = re.escape(project_id)
    literal = re.compile(rf"(?:[A-Za-z_]\w*\.)?{col}\s*=\s*'{pid}'", re.IGNORECASE)
    bind = re.compile(rf"(?:[A-Za-z_]\w*\.)?{col}\s*=\s*:project_id\b", re.IGNORECASE)
    return bool(literal.search(sql) or bind.search(sql))


def validate_raw_query(sql: str, project_id: str) -> str:
    """Validate a free-form agent ``SELECT`` for read-only, project-scoped access.

    Returns the normalized SQL (trailing semicolon stripped) on success.

    Raises:
        QueryIsolationError: if the statement is not a single read-only SELECT,
            references an unknown table, or touches a project-scoped table
            without an explicit ``project_id`` predicate matching ``project_id``.
    """
    if not sql or not sql.strip():
        raise QueryIsolationError("Empty query")

    stripped = sql.strip().rstrip(";").strip()
    lowered = stripped.lower()

    # Single statement only — no stacked queries.
    if ";" in stripped:
        raise QueryIsolationError("Multiple statements are not allowed")

    # No comments (used to smuggle past keyword checks).
    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        raise QueryIsolationError("SQL comments are not allowed")

    # Must be a plain SELECT (CTEs / WITH are rejected to shrink attack surface).
    if not lowered.startswith("select"):
        raise QueryIsolationError("Only SELECT statements are allowed")

    # Forbidden write/DDL keywords (word-boundary matched).
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", lowered):
            raise QueryIsolationError(f"Keyword '{kw}' is not allowed in agent queries")

    # Forbidden functions / extensions.
    for fn in _FORBIDDEN_FUNCTIONS:
        if fn in lowered:
            raise QueryIsolationError(f"Function '{fn}' is not allowed")

    tables = _referenced_tables(stripped)
    if not tables:
        raise QueryIsolationError("Could not identify any table in the query")

    touches_scoped = False
    for table in tables:
        if table in GLOBAL_READONLY_TABLES:
            continue
        if table == PROJECT_ROOT_TABLE:
            touches_scoped = True
            if not _has_project_predicate(stripped, "id", project_id):
                raise QueryIsolationError(f"Query on '{table}' must filter by id = '{project_id}'")
            continue
        if table in PROJECT_SCOPED_TABLES:
            touches_scoped = True
            if not _has_project_predicate(stripped, "project_id", project_id):
                raise QueryIsolationError(
                    f"Query on project-scoped table '{table}' must filter by "
                    f"project_id = '{project_id}'"
                )
            continue
        # Default-deny: unknown / sensitive table (users, conversations, ...).
        raise QueryIsolationError(f"Table '{table}' is not readable by agents (default-deny)")

    # Best-effort tautology rejection only matters once a scoped predicate exists.
    if touches_scoped:
        for pattern in _TAUTOLOGY_RES:
            if pattern.search(stripped):
                raise QueryIsolationError(
                    "Suspicious boolean tautology detected; use structured "
                    "query mode (table + filters) instead"
                )

    return stripped


def build_scoped_query(
    project_id: str,
    table: str,
    columns: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 50,
) -> tuple[str, dict[str, Any]]:
    """Build a guaranteed project-scoped, parameterised ``SELECT``.

    This is the safe, recommended path for agent ``db_query`` calls. The
    ``project_id = :project_id`` predicate is always injected, column and table
    identifiers are validated against an allowlist/identifier rule, and all
    values are bound parameters (never interpolated).

    Returns:
        ``(sql, params)`` ready for ``sqlalchemy.text(sql)`` execution.

    Raises:
        QueryIsolationError: for unknown tables or invalid identifiers.
    """
    table_norm = table.strip().strip('"').lower()
    if table_norm not in PROJECT_SCOPED_TABLES:
        raise QueryIsolationError(
            f"Structured queries are only allowed on project-scoped tables, not '{table}'"
        )

    # Columns
    if not columns:
        select_cols = "*"
    else:
        for col in columns:
            if not _IDENTIFIER_RE.match(col):
                raise QueryIsolationError(f"Invalid column identifier: {col!r}")
        select_cols = ", ".join(columns)

    params: dict[str, Any] = {"project_id": project_id}
    where_clauses = ["project_id = :project_id"]

    if filters:
        for i, (col, value) in enumerate(filters.items()):
            if not _IDENTIFIER_RE.match(col):
                raise QueryIsolationError(f"Invalid filter column: {col!r}")
            param_name = f"f_{i}"
            where_clauses.append(f"{col} = :{param_name}")
            params[param_name] = value

    safe_limit = max(1, min(int(limit or 50), _MAX_QUERY_ROWS))
    sql = (
        f"SELECT {select_cols} FROM {table_norm} "
        f"WHERE {' AND '.join(where_clauses)} LIMIT {safe_limit}"
    )
    return sql, params


# ── ASGI middleware ─────────────────────────────────────────────────────────

_PATH_PROJECT_RE = re.compile(r"/projects/([0-9a-fA-F-]{36})(?:/|$)")


def extract_project_id_from_path(path: str) -> str | None:
    """Return the project UUID embedded in ``/projects/{id}/...`` paths, if any."""
    match = _PATH_PROJECT_RE.search(path or "")
    return match.group(1) if match else None


class ProjectIsolationMiddleware:
    """Pure-ASGI middleware that pins the request's project_id onto state.

    It does NOT perform authorization (that is the ``require_project_permission``
    dependency's job) — it provides defense-in-depth *context*: a single,
    reliable place where the active project is recorded for logging, auditing,
    and downstream isolation guards. Implemented as a plain ASGI callable to
    avoid a Starlette ``BaseHTTPMiddleware`` import (keeps this module testable
    without third-party packages).
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") in ("http", "websocket"):
            project_id = extract_project_id_from_path(scope.get("path", ""))
            if project_id is not None:
                state = scope.setdefault("state", {})
                if isinstance(state, dict):
                    state["project_id"] = project_id
        await self.app(scope, receive, send)
