"""Tests for AppSettingService.get_ai_config — provider key sync.

After adding the Cerebras and Google AI Studio runtimes, ``get_ai_config`` must
expose ``cerebras_api_key`` / ``google_api_key`` so the admin UI and the
model_fallback DB-key injection stay in sync with the env-var fallback.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.app_setting import AppSettingService


def _row(key: str, value: str) -> SimpleNamespace:
    return SimpleNamespace(key=key, value=value)


@pytest.mark.anyio
async def test_get_ai_config_exposes_new_provider_keys_from_env():
    svc = AppSettingService(db=AsyncMock())
    with (
        patch("app.repositories.app_setting_repo.list_all", new=AsyncMock(return_value=[])),
        patch("app.core.config.settings.CEREBRAS_API_KEY", "csk-env", create=True),
        patch("app.core.config.settings.GOOGLE_API_KEY", "AIza-env", create=True),
    ):
        cfg = await svc.get_ai_config()

    # Both keys are present in the returned config (required by the API + fallback layer).
    assert "cerebras_api_key" in cfg
    assert "google_api_key" in cfg
    # With no DB row, they fall back to the env var.
    assert cfg["cerebras_api_key"] == "csk-env"
    assert cfg["google_api_key"] == "AIza-env"


@pytest.mark.anyio
async def test_get_ai_config_db_row_overrides_env_for_new_keys():
    rows = [
        _row("ai.cerebras_api_key", "csk-db"),
        _row("ai.google_api_key", ""),  # explicitly cleared via UI
    ]
    svc = AppSettingService(db=AsyncMock())
    with (
        patch("app.repositories.app_setting_repo.list_all", new=AsyncMock(return_value=rows)),
        patch("app.core.config.settings.CEREBRAS_API_KEY", "csk-env", create=True),
        patch("app.core.config.settings.GOOGLE_API_KEY", "AIza-env", create=True),
    ):
        cfg = await svc.get_ai_config()

    # DB row wins over env, including an explicit empty-string clear.
    assert cfg["cerebras_api_key"] == "csk-db"
    assert cfg["google_api_key"] == ""
