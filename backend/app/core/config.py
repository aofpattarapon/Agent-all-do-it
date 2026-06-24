"""Application configuration using Pydantic BaseSettings."""
# ruff: noqa: I001 - Imports structured for Jinja2 template conditionals

from pathlib import Path
from typing import Literal

from pydantic import computed_field, field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_env_file() -> Path | None:
    """Find .env file in current or parent directories."""
    current = Path.cwd()
    for path in [current, current.parent]:
        env_file = path / ".env"
        if env_file.exists():
            return env_file
    return None


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_ignore_empty=True,
        extra="ignore",
    )

    # === Project ===
    PROJECT_NAME: str = "pixel_dream_agent"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: Literal["development", "local", "staging", "production"] = "local"
    TIMEZONE: str = "UTC"  # IANA timezone (e.g. "UTC", "Europe/Warsaw", "America/New_York")
    MODELS_CACHE_DIR: Path = Path("./models_cache")
    MEDIA_DIR: Path = Path("./media")
    MAX_UPLOAD_SIZE_MB: int = 50  # Max file upload size in MB
    # Soft per-org storage cap surfaced on /billing — not enforced yet (5 GB).
    STORAGE_SOFT_LIMIT_BYTES: int = 5 * 1024 * 1024 * 1024

    # === Logfire ===
    LOGFIRE_TOKEN: str | None = None
    LOGFIRE_SERVICE_NAME: str = "pixel_dream_agent"
    LOGFIRE_ENVIRONMENT: str = "development"

    # === Server Ports ===
    BACKEND_PORT: int = 8100
    FRONTEND_PORT: int = 3100
    FLOWER_PORT: int = 5556

    # === Database (PostgreSQL async) ===
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "pixel_dream_agent"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URL(self) -> str:
        """Build async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Build sync PostgreSQL connection URL (for Alembic)."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Pool configuration — 14 concurrent agents x 1 conn each + API overhead; overflow handles bursts
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30

    # === Auth (SECRET_KEY for JWT/Session/Admin) ===
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        """Validate SECRET_KEY is secure in production."""
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        # Get environment from values if available
        env = info.data.get("ENVIRONMENT", "local") if info.data else "local"
        if v == "change-me-in-production-use-openssl-rand-hex-32" and env == "production":
            raise ValueError(
                "SECRET_KEY must be changed in production! "
                "Generate a secure key with: openssl rand -hex 32"
            )
        return v

    # === Agent code-execution tool ===
    # The `code_exec` tool runs Python in a host subprocess and is NOT a real sandbox
    # (host RCE risk). Disabled by default; only enable in a trusted/isolated environment.
    ENABLE_CODE_EXEC: bool = False

    # === Secret store encryption (Fernet, at-rest for the `secrets` table) ===
    # Optional. If unset, a key is derived deterministically from SECRET_KEY so existing
    # deployments work without a new env var. Set a dedicated Fernet key (openssl rand and
    # urlsafe-base64, or `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
    # to rotate it independently of SECRET_KEY.
    SECRET_ENCRYPTION_KEY: str = ""

    # === JWT Settings ===
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 30 minutes
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # Public URL of the frontend; used to build OAuth redirect targets and
    # Stripe checkout/portal return URLs. Always declared (not gated) because
    # the billing model_validator references it unconditionally.
    FRONTEND_URL: str = "http://localhost:3000"

    # === Auth (API Key) ===
    API_KEY: str = "change-me-in-production"
    API_KEY_HEADER: str = "X-API-Key"

    @field_validator("API_KEY")
    @classmethod
    def validate_api_key(cls, v: str, info: ValidationInfo) -> str:
        """Validate API_KEY is set in production."""
        env = info.data.get("ENVIRONMENT", "local") if info.data else "local"
        if v == "change-me-in-production" and env == "production":
            raise ValueError(
                "API_KEY must be changed in production! "
                "Generate a secure key with: openssl rand -hex 32"
            )
        return v

    # === Redis ===
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6380
    REDIS_PASSWORD: str | None = None
    REDIS_DB: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URL(self) -> str:
        """Build Redis connection URL."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # === Celery ===
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # === Crypto Trade Pipeline ===
    PIPELINE_STEP_DELAY_SECONDS: int = 4  # inter-step pacing (anti-rate-limit)
    PIPELINE_WARMUP_TRADES: int = 10  # paper trades before winrate gate enforced
    PIPELINE_WINRATE_THRESHOLD: float = 60.0  # auto-execute if winrate >= this
    # Warmup-window policy (W22E): how the Auto winrate gate behaves while
    # closed_count < PIPELINE_WARMUP_TRADES. One of: auto_execute | pending_approval |
    # validation_only. Safe default is pending_approval; any invalid/unreadable value
    # fails closed to pending_approval (see app.services.warmup_policy). Declared as a
    # plain str (not Literal) so an invalid env value never crashes boot — it is
    # validated/normalized at resolution time, never silently becoming auto_execute.
    PIPELINE_WARMUP_MODE: str = "pending_approval"

    # When True (default), re-seeding the crypto workflows is idempotent w.r.t. operator
    # enable/disable decisions: existing schedules keep their current `enabled` value, and a
    # newly created schedule defaults to disabled unless it is the Position Monitor (always-on
    # safety observer). When False, the seed restores the legacy behavior of force-enabling
    # every cron schedule it touches. Default True is the safe posture — it stops a reseed from
    # silently re-arming order-capable schedules (Market Watch / Screeners / Proposal pipeline).
    PRESERVE_SCHEDULE_ENABLED_STATE: bool = True

    # === W29 Watch Cron Observer (Phase W31A) ===
    # A STRICTLY READ-ONLY periodic beat task (every 15m) that evaluates the HAWK
    # condition watch and logs the advisory posture. It never dispatches a workflow,
    # creates an order/proposal/execution/risk_ack, or mutates validation_only — it only
    # reads and logs (see app.services.w29_watch_observer). Off-switch: set this to False
    # and restart celery_beat; the task then short-circuits before touching the DB.
    W29_WATCH_OBSERVER_ENABLED: bool = True
    # Read-only evaluation scope for the observer (the crypto trading project).
    W29_WATCH_OBSERVER_PROJECT_ID: str = "288bc95a-b4da-46e7-bdfa-b5630233f586"

    # === DEMO Guarded Auto-Approval (Phase W31E) ===
    # A guarded, DEMO-ONLY auto-approval policy (``DEMO_GUARDED_AUTO_APPROVAL``). SHIPS
    # DISABLED. When enabled it can transform "fresh live READY + all guards pass + DEMO +
    # within caps" into a single, fully-logged ``AUTO_APPROVED_DEMO`` decision authorising
    # ONE controlled DEMO attempt. It NEVER weakens HAWK/SAGE/kill-switch/preflight (those
    # downstream gates still run unchanged during execution), NEVER enables LIVE, NEVER
    # creates a risk_ack, NEVER flips validation_only globally, and NEVER uses the retry
    # endpoint. Two independent off-switches, both default False:
    #   * AUTO_APPROVAL_ENABLED       — lets the evaluator RUN and LOG decisions (no order).
    #   * AUTO_APPROVAL_PLACE_ORDERS  — second gate required before any order placement.
    # Order-placement wiring is intentionally deferred to an owner-reviewed follow-up; with
    # the current build, an AUTO_APPROVED_DEMO decision is logged but NO order is placed.
    AUTO_APPROVAL_ENABLED: bool = False
    AUTO_APPROVAL_PLACE_ORDERS: bool = False
    AUTO_APPROVAL_SCOPE: str = "demo_ready_watch_only"
    AUTO_APPROVAL_PROJECT_ID: str = "288bc95a-b4da-46e7-bdfa-b5630233f586"
    AUTO_APPROVAL_MAX_NOTIONAL_USDT: float = 50.0
    AUTO_APPROVAL_MAX_OPEN_POSITIONS: int = 1
    AUTO_APPROVAL_MAX_ORDERS_PER_DAY: int = 1
    AUTO_APPROVAL_READY_CONFIRMATION_TICKS: int = 2
    AUTO_APPROVAL_READY_MAX_AGE_SECONDS: int = 300
    # W31H — durable multi-tick READY confirmation (read-only state in the Celery broker Redis).
    # Max gap between two ticks that still counts as "consecutive" (default 16 min; the evaluator
    # runs every 15 min, so a single non-READY tick in between breaks the streak). TTL auto-expires
    # an idle counter. Neither tunable can place an order — they only gate readiness.
    AUTO_APPROVAL_READY_CONFIRM_MAX_GAP_SECONDS: int = 960
    AUTO_APPROVAL_READY_CONFIRM_TTL_SECONDS: int = 1200
    AUTO_APPROVAL_COOLDOWN_MINUTES: int = 60
    AUTO_APPROVAL_REQUIRE_EXCHANGE_FLAT: bool = True
    AUTO_APPROVAL_REQUIRE_HAWK_2_OF_3: bool = True
    AUTO_APPROVAL_REQUIRE_SAGE_APPROVAL: bool = True
    AUTO_APPROVAL_REQUIRE_SL_TP_RR_PREFLIGHT: bool = True
    AUTO_APPROVAL_REQUIRE_DEMO_MODE: bool = True
    # If the kill-switch consecutive-loss gate is armed and no ack exists, block auto-approval
    # (owner must separately/explicitly choose any consecutive-loss ack — never auto-created).
    AUTO_APPROVAL_BLOCK_IF_CONSECUTIVE_LOSS_ACK_MISSING: bool = True

    # === AI Agent (langgraph, all) ===
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    MOONSHOT_API_KEY: str | None = None  # Moonshot AI (Kimi) — https://platform.moonshot.cn
    GROQ_API_KEY: str | None = None  # Groq Cloud — https://console.groq.com/keys
    CEREBRAS_API_KEY: str | None = None  # Cerebras Cloud — https://cloud.cerebras.ai
    OLLAMA_URL: str = "http://localhost:11434"  # Remote Ollama: set to http://<host>:<port>
    # Multi-provider: model can come from any installed SDK. Prefix with the
    # provider name (`openai/gpt-5.5`, `anthropic/claude-opus-4-7`,
    # `google/gemini-2.5-flash`, `openrouter/anthropic/claude-opus-4-7`)
    # so the dispatcher in agents/assistant.py routes to the right backend.
    AI_MODEL: str = "openai/gpt-5.5"
    AI_TEMPERATURE: float = 0.7
    AI_THINKING_ENABLED: bool = False
    AI_THINKING_EFFORT: str = "medium"  # "low", "medium", "high"
    AI_AVAILABLE_MODELS: list[str] = [
        # OpenAI
        "openai/gpt-5.5",
        "openai/gpt-5.5-pro",
        "openai/gpt-5.4",
        "openai/gpt-5-mini",
        "openai/gpt-4.1",
        # Anthropic
        "anthropic/claude-opus-4-7",
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-haiku-4-5-20251001",
        # Google
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
        # OpenRouter (proxies many providers)
        "openrouter/anthropic/claude-opus-4-7",
        "openrouter/deepseek/deepseek-r1",
        "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
        "openrouter/owl-alpha",
    ]
    AI_FRAMEWORK: str = "langgraph"
    LLM_PROVIDER: str = "all"

    # === LangSmith Observability ===
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_API_KEY: str | None = None
    LANGCHAIN_PROJECT: str = "pixel_dream_agent"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    # === CORS ===
    CORS_ORIGINS: list[str] = [
        "http://localhost:3100",
        "http://localhost:8080",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: list[str], info: ValidationInfo) -> list[str]:
        """Warn if CORS_ORIGINS is too permissive in production."""
        env = info.data.get("ENVIRONMENT", "local") if info.data else "local"
        if "*" in v and env == "production":
            raise ValueError(
                "CORS_ORIGINS cannot contain '*' in production! Specify explicit allowed origins."
            )
        return v


settings = Settings()
