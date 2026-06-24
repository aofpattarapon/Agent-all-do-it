"""Cerebras API runtime adapter — very fast inference via Cerebras Cloud.

Cerebras exposes an OpenAI-compatible API at https://api.cerebras.ai/v1.
Set CEREBRAS_API_KEY in .env or via Admin → Settings to use this adapter.
High free-tier RPD and ~128k context make it a good primary for the
high-reasoning crypto agents (market_regime, hawk_trend, sage, post_trade_review).
"""

from app.core.config import settings
from app.services.runtime._utils import API_CALL_TIMEOUT_SECONDS

CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
DEFAULT_MODEL = "llama-3.3-70b"


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
    api_key: str | None = None,
) -> tuple[str, dict]:
    """Call the Cerebras Cloud API (OpenAI-compatible).

    ``api_key`` is injected by ``run_with_fallback`` from the DB-stored value so
    that keys saved via the admin UI take effect without a container restart.
    Falls back to the ``CEREBRAS_API_KEY`` env var when no override is provided.
    """
    import openai

    resolved_key = api_key or getattr(settings, "CEREBRAS_API_KEY", "") or ""
    if not resolved_key:
        raise RuntimeError("CEREBRAS_API_KEY missing — set it in Admin → Settings or in .env")

    # max_retries=0: model_fallback.py owns all retry/backoff so the SDK's built-in
    # retries don't compound with ours and burn the rate-limit budget before fallback.
    client = openai.AsyncOpenAI(
        api_key=resolved_key,
        base_url=CEREBRAS_BASE_URL,
        max_retries=0,
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
    return text or "", {"runtime": "cerebras-api", "model": resolved_model, "tokens_used": tokens}


def healthcheck() -> dict:
    """Check whether the Cerebras API is usable (key configured + openai SDK installed)."""
    available = bool(getattr(settings, "CEREBRAS_API_KEY", ""))
    detail = ""
    if not available:
        detail = "CEREBRAS_API_KEY not set"
    else:
        try:
            import openai  # noqa: F401
        except Exception as exc:
            available = False
            detail = f"openai SDK not installed: {exc}"
    return {"kind": "cerebras-api", "available": available, "detail": detail}
