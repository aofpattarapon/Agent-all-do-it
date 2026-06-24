"""OpenAI API runtime adapter."""

from app.core.config import settings
from app.services.runtime._utils import API_CALL_TIMEOUT_SECONDS


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, dict]:
    """Call the OpenAI Chat Completions API.

    Returns (output_text, metadata) where metadata may include tokens_used.
    """
    import openai

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured (401 unauthorized)")

    client = openai.AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        max_retries=0,  # run_with_fallback owns retry/backoff — no hidden SDK retries
    )
    resolved_model = model or "gpt-4o"

    messages = []
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
    return text, {"runtime": "openai-api", "model": resolved_model, "tokens_used": tokens}


def healthcheck() -> dict:
    """Check whether the OpenAI API is usable (key configured + SDK installed)."""
    detail = ""
    available = bool(settings.OPENAI_API_KEY)
    if not available:
        detail = "OPENAI_API_KEY not set"
    else:
        try:
            import openai  # noqa: F401
        except Exception as exc:
            available = False
            detail = f"openai SDK not installed: {exc}"
    return {"kind": "openai-api", "available": available, "detail": detail}
