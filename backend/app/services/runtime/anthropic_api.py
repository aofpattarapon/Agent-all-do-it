"""Anthropic API runtime adapter."""

from app.core.config import settings


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, dict]:
    """Call the Anthropic Messages API.

    Returns (output_text, metadata) where metadata may include tokens_used.
    """
    import anthropic

    if not settings.ANTHROPIC_API_KEY:
        # Raised (not caught) so the executor's LLMErrorClassifier can map it to auth_error.
        raise RuntimeError("ANTHROPIC_API_KEY is not configured (401 unauthorized)")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    resolved_model = model or "claude-haiku-4-5-20251001"

    response = await client.messages.create(
        model=resolved_model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt or "You are a helpful assistant.",
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text if response.content else ""
    tokens = None
    if response.usage:
        tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
    return text, {"runtime": "anthropic-api", "model": resolved_model, "tokens_used": tokens}


def healthcheck() -> dict:
    """Check whether the Anthropic API is usable (key configured + SDK installed)."""
    detail = ""
    available = bool(settings.ANTHROPIC_API_KEY)
    if not available:
        detail = "ANTHROPIC_API_KEY not set"
    else:
        try:
            import anthropic  # noqa: F401
        except Exception as exc:
            available = False
            detail = f"anthropic SDK not installed: {exc}"
    return {"kind": "anthropic-api", "available": available, "detail": detail}
