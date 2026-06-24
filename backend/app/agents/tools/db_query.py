"""Read-only, **project-scoped** database query tool for agents.

This tool previously ran arbitrary ``SELECT`` over the whole database, which
would let an agent in Project A read Project B's rows (a cross-project data
leak). It now enforces project isolation via ``app.core.project_isolation`` and
offers two modes:

* **Structured (preferred):** pass ``table`` (+ optional ``columns`` /
  ``filters``). The query is *built* with a mandatory ``project_id`` predicate
  and fully parameterised values — injection-proof by construction.
* **Raw (guarded):** pass a single ``sql`` SELECT. It is validated by the
  isolation guard, which requires an explicit ``project_id`` predicate for any
  project-scoped table and default-denies unknown/sensitive tables.

``project_id`` is **injected by the agent runtime from the run context** — it
must never be taken from the LLM — so the model cannot widen its own scope.
"""

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.project_isolation import (
    QueryIsolationError,
    build_scoped_query,
    validate_raw_query,
)

logger = logging.getLogger(__name__)

_MAX_ROWS = 100


async def run_query(
    db: AsyncSession,
    *,
    project_id: str | UUID,
    sql: str | None = None,
    table: str | None = None,
    columns: list[str] | None = None,
    filters: dict | None = None,
    limit: int = 50,
) -> dict:
    """Execute a read-only, project-scoped query.

    Args:
        db: An async SQLAlchemy session.
        project_id: Runtime-injected project scope (NOT supplied by the LLM).
        sql: Raw-mode single ``SELECT`` statement (guarded).
        table: Structured-mode project-scoped table name.
        columns: Optional column allowlist for structured mode.
        filters: Optional ``{column: value}`` equality filters for structured mode.
        limit: Row cap (clamped to 100).

    Returns:
        ``{"ok": True, "columns": [...], "rows": [...], "row_count": n}`` on
        success, or ``{"ok": False, "error": "..."}`` on failure / policy block.
    """
    if not project_id:
        return {"ok": False, "error": "project_id is required (runtime-injected)"}
    pid = str(project_id)

    try:
        if table is not None:
            query, params = build_scoped_query(pid, table, columns, filters, limit)
            result = await db.execute(text(query), params)
        elif sql:
            safe_sql = validate_raw_query(sql, pid)
            result = await db.execute(text(safe_sql))
        else:
            return {
                "ok": False,
                "error": "Provide 'table' (structured mode) or 'sql' (raw mode).",
            }
    except QueryIsolationError as exc:
        logger.warning("db_query blocked by isolation guard (project=%s): %s", pid, exc)
        return {"ok": False, "error": f"Query blocked by isolation guard: {exc}"}
    except Exception as exc:
        logger.warning("run_query failed: %s", exc)
        return {"ok": False, "error": str(exc)}

    columns_out = list(result.keys())
    mappings = result.mappings().fetchmany(_MAX_ROWS)
    rows = [dict(row) for row in mappings]
    return {"ok": True, "columns": columns_out, "rows": rows, "row_count": len(rows)}
