"""Kimi API runtime adapter — Moonshot AI via OpenAI-compatible REST API.

Moonshot AI exposes an OpenAI-compatible API at https://api.moonshot.cn/v1.
Set MOONSHOT_API_KEY in your environment to use this adapter.
"""

from app.core.config import settings
from app.services.runtime._utils import API_CALL_TIMEOUT_SECONDS

MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "moonshot-v1-8k"


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
    api_key: str | None = None,
) -> tuple[str, dict]:
    """Call the Moonshot AI API (OpenAI-compatible).

    ``api_key`` is injected by ``run_with_fallback`` from the DB-stored value so
    that keys saved via the admin UI take effect without a container restart.
    Falls back to the ``MOONSHOT_API_KEY`` env var when no override is provided.
    """
    import openai

    resolved_key = api_key or settings.MOONSHOT_API_KEY or ""
    if not resolved_key:
        raise RuntimeError("MOONSHOT_API_KEY missing — set it in Admin → Settings or in .env")

    client = openai.AsyncOpenAI(
        api_key=resolved_key,
        base_url=MOONSHOT_BASE_URL,
        max_retries=0,  # run_with_fallback owns retry/backoff — no hidden SDK retries
    )
    resolved_model = model or DEFAULT_MODEL

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model=resolved_model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=messages,
        timeout=API_CALL_TIMEOUT_SECONDS,
    )
    text = response.choices[0].message.content if response.choices else ""
    tokens = None
    if response.usage:
        tokens = (response.usage.prompt_tokens or 0) + (response.usage.completion_tokens or 0)
    return text or "", {"runtime": "kimi-api", "model": resolved_model, "tokens_used": tokens}


def healthcheck() -> dict:
    """Check whether the Moonshot API is usable (key configured + openai SDK installed)."""
    available = bool(settings.MOONSHOT_API_KEY)
    detail = ""
    if not available:
        detail = "MOONSHOT_API_KEY not set"
    else:
        try:
            import openai  # noqa: F401
        except Exception as exc:
            available = False
            detail = f"openai SDK not installed: {exc}"
    return {"kind": "kimi-api", "available": available, "detail": detail}
