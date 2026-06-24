"""Tests for Celery worker tasks — soft time-limit handling.

When a run hits ``task_soft_time_limit``, the task must mark its run ``failed``
(so ``schedule_runner``'s per-workflow overlap guard releases and the next cron
tick can fire) and must NOT retry (a timed-out run would just re-hang).
"""

from unittest.mock import patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from app.worker import tasks


def _raise_soft_limit(coro=None):
    """Stand-in for asyncio.run: close the (unawaited) coroutine, then time out."""
    if coro is not None and hasattr(coro, "close"):
        coro.close()
    raise SoftTimeLimitExceeded()


@pytest.mark.parametrize(
    "task",
    [tasks.execute_run_task, tasks.resume_run_task, tasks.override_approve_run_task],
)
def test_run_task_marks_run_failed_on_soft_timeout(task):
    with (
        patch.object(tasks.asyncio, "run", side_effect=_raise_soft_limit),
        patch.object(tasks, "_mark_run_failed") as mark,
        pytest.raises(SoftTimeLimitExceeded),
    ):
        task("run-id", "project-id")
    mark.assert_called_once()
    args = mark.call_args.args
    assert args[0] == "run-id"
    assert args[1] == "project-id"
