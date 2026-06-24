"""Phase W31A — read-only W29 Watch observer Celery beat task tests.

The beat task must:
  * short-circuit (no DB work) when the observer is disabled via settings,
  * run the observer coroutine when enabled,
  * fail SAFE on any Watch/data error (log, never raise into a retry/escalation),
  * contain no order/dispatch capability in its body.

It never dispatches a workflow, creates a risk_ack, or sends an exchange order — there is
no such code path to reach.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.worker import tasks


def _close_and_return(coro=None):
    """Stand-in for asyncio.run: close the (unawaited) coroutine, then return cleanly."""
    if coro is not None and hasattr(coro, "close"):
        coro.close()


def _close_and_raise(coro=None):
    """Stand-in for asyncio.run: close the coroutine, then raise to simulate a failure."""
    if coro is not None and hasattr(coro, "close"):
        coro.close()
    raise RuntimeError("simulated watch/data failure")


def test_observer_task_disabled_short_circuits(monkeypatch):
    monkeypatch.setattr(settings, "W29_WATCH_OBSERVER_ENABLED", False)
    with patch.object(tasks.asyncio, "run") as run:
        tasks.w29_watch_observer_task()
    run.assert_not_called()


def test_observer_task_enabled_invokes_async_run(monkeypatch):
    monkeypatch.setattr(settings, "W29_WATCH_OBSERVER_ENABLED", True)
    with patch.object(tasks.asyncio, "run", side_effect=_close_and_return) as run:
        tasks.w29_watch_observer_task()
    run.assert_called_once()


def test_observer_task_failure_is_safe(monkeypatch):
    monkeypatch.setattr(settings, "W29_WATCH_OBSERVER_ENABLED", True)
    # A Watch/data failure must NOT propagate (no retry storm, no escalation).
    with patch.object(tasks.asyncio, "run", side_effect=_close_and_raise):
        result = tasks.w29_watch_observer_task()
    assert result is None


# ── Static read-only proof on the task body ──────────────────────────────────

_FORBIDDEN_TOKENS = (
    "place_order",
    "create_order",
    "cancel_order",
    "_dispatch_run",
    "send_task",
    "execute_run",
    "RunExecutor",
    "resume_approved",
    "resume_from_blocked",
    "risk_ack",
)


def _task_function_source() -> str:
    """Unparse the task's executable body, dropping its docstring.

    The docstring intentionally names the capabilities the observer must NOT have
    (risk_ack, order, dispatch, …), so it is excluded from the forbidden-token scan.
    """
    src = Path(tasks.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "w29_watch_observer_task":
            body = list(node.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            return "\n".join(ast.unparse(n) for n in body)
    raise AssertionError("w29_watch_observer_task not found")


def test_observer_task_body_has_no_order_or_dispatch_tokens():
    body = _task_function_source()
    for token in _FORBIDDEN_TOKENS:
        assert token not in body, f"observer task body unexpectedly references {token!r}"
    # It reaches the watch only through the read-only observer service.
    assert "observe_once" in body
