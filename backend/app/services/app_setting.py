"""AppSetting service — global runtime configuration."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.app_setting import AppSetting
from app.repositories import app_setting_repo


class AppSettingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self) -> list[AppSetting]:
        return await app_setting_repo.list_all(self.db)

    async def get(self, key: str, default: str = "") -> str:
        return await app_setting_repo.get_value(self.db, key, default)

    async def set(self, key: str, value: str) -> AppSetting:
        return await app_setting_repo.upsert(self.db, key=key, value=value)

    async def get_trading_mode_config(self) -> dict[str, str | None]:
        """Return stored trading-mode config, or None where the DB has no override."""
        rows = await app_setting_repo.list_all(self.db)
        config = {r.key: r.value for r in rows if r.key.startswith("trading.")}
        return {
            "trading_mode": config.get("trading.trading_mode"),
            "exchange_mode": config.get("trading.exchange_mode"),
        }

    async def set_trading_mode_config(self, trading_mode: str, exchange_mode: str) -> None:
        """Persist a validated trading-mode pair to the database."""
        await app_setting_repo.upsert(
            self.db,
            key="trading.trading_mode",
            value=trading_mode.upper().strip(),
            description="Runtime TRADING_MODE override (PAPER/DEMO/TESTNET/LIVE)",
        )
        await app_setting_repo.upsert(
            self.db,
            key="trading.exchange_mode",
            value=exchange_mode.lower().strip(),
            description="Runtime EXCHANGE_MODE override (paper/demo/testnet/live)",
        )

    async def get_ai_config(self) -> dict:
        """Return the full AI backend config as a dict."""
        rows = await app_setting_repo.list_all(self.db)
        config = {r.key: r.value for r in rows if r.key.startswith("ai.")}
        from app.core.config import settings as env_settings

        # For keys that can be cleared via the UI, distinguish "never set" (no DB row)
        # from "explicitly cleared" (DB row with empty value). Use 'in config' as sentinel.
        moonshot_api_key = (
            config["ai.moonshot_api_key"]
            if "ai.moonshot_api_key" in config
            else (getattr(env_settings, "MOONSHOT_API_KEY", "") or "")
        )
        groq_api_key = (
            config["ai.groq_api_key"]
            if "ai.groq_api_key" in config
            else (getattr(env_settings, "GROQ_API_KEY", "") or "")
        )
        cerebras_api_key = (
            config["ai.cerebras_api_key"]
            if "ai.cerebras_api_key" in config
            else (getattr(env_settings, "CEREBRAS_API_KEY", "") or "")
        )
        google_api_key = (
            config["ai.google_api_key"]
            if "ai.google_api_key" in config
            else (getattr(env_settings, "GOOGLE_API_KEY", "") or "")
        )
        openrouter_api_key = (
            config["ai.openrouter_api_key"]
            if "ai.openrouter_api_key" in config
            else (getattr(env_settings, "OPENROUTER_API_KEY", "") or "")
        )
        ollama_url = (
            config["ai.ollama_url"]
            if "ai.ollama_url" in config
            else (getattr(env_settings, "OLLAMA_URL", "") or "http://localhost:11434")
        )
        return {
            "default_backend": config.get("ai.default_backend", "claude-cli"),
            "anthropic_api_key": config.get("ai.anthropic_api_key", ""),
            "default_model": config.get("ai.default_model", "claude-haiku-4-5-20251001"),
            "auto_fallback": config.get("ai.auto_fallback", "true") == "true",
            "moonshot_api_key": moonshot_api_key,
            "groq_api_key": groq_api_key,
            "cerebras_api_key": cerebras_api_key,
            "google_api_key": google_api_key,
            "openrouter_api_key": openrouter_api_key,
            "ollama_url": ollama_url,
        }
