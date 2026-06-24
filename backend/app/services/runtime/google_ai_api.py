"""Google AI Studio (Gemini) runtime adapter — 1M-context free-tier models.

Google AI Studio exposes an OpenAI-compatible endpoint at
https://generativelanguage.googleapis.com/v1beta/openai/.
Set GOOGLE_API_KEY in .env or via Admin → Settings to use this adapter.
The 1M-token context window makes it the right primary for agents that read
long inputs (news_monitor, trade_proposal) without truncation.
"""

from app.core.config import settings
from app.services.runtime._utils import API_CALL_TIMEOUT_SECONDS

GOOGLE_AI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-2.0-flash"


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
    api_key: str | None = None,
) -> tuple[str, dict]:
    """Call Google AI Studio (Gemini) via its OpenAI-compatible endpoint.

    ``api_key`` is injected by ``run_with_fallback`` from the DB-stored value so
    that keys saved via the admin UI take effect without a container restart.
    Falls back to the ``GOOGLE_API_KEY`` env var when no override is provided.
    """
    import openai

    resolved_key = api_key or getattr(settings, "GOOGLE_API_KEY", "") or ""
    if not resolved_key:
        raise RuntimeError("GOOGLE_API_KEY missing — set it in Admin → Settings or in .env")

    # max_retries=0: model_fallback.py owns all retry/backoff so the SDK's built-in
    # retries don't compound with ours and burn the rate-limit budget before fallback.
    client = openai.AsyncOpenAI(
        api_key=resolved_key,
        base_url=GOOGLE_AI_BASE_URL,
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
    return text or "", {
        "runtime": "google-ai-studio",
        "model": resolved_model,
        "tokens_used": tokens,
    }


def healthcheck() -> dict:
    """Check whether Google AI Studio is usable (key configured + openai SDK installed)."""
    available = bool(getattr(settings, "GOOGLE_API_KEY", ""))
    detail = ""
    if not available:
        detail = "GOOGLE_API_KEY not set"
    else:
        try:
            import openai  # noqa: F401
        except Exception as exc:
            available = False
            detail = f"openai SDK not installed: {exc}"
    return {"kind": "google-ai-studio", "available": available, "detail": detail}
