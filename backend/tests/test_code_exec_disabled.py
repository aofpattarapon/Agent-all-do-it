"""code_exec is disabled by default unless ENABLE_CODE_EXEC is set (C11)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agents.tools import code_exec
from app.core.config import settings


@pytest.mark.anyio
async def test_execute_code_disabled_by_default() -> None:
    with patch.object(settings, "ENABLE_CODE_EXEC", False):
        result = await code_exec.execute_code("print('hi')")
    assert result["exit_code"] == -1
    assert "disabled" in result["stderr"].lower()


@pytest.mark.anyio
async def test_execute_code_runs_when_enabled() -> None:
    with patch.object(settings, "ENABLE_CODE_EXEC", True):
        result = await code_exec.execute_code("print('hi')")
    assert result["exit_code"] == 0
    assert "hi" in result["stdout"]
