"""Shared helpers for runtime adapters."""

# Per-call wall-clock ceiling for hosted LLM API adapters. Without this the OpenAI
# SDK default (~600s) lets a single hung free-provider call stall the whole serial
# agent pipeline past the Celery soft limit and kill the run. run_with_fallback owns
# retry/backoff; this only bounds one individual call.
API_CALL_TIMEOUT_SECONDS = 90


def combine_prompts(system_prompt: str, prompt: str) -> str:
    """Merge system prompt and user prompt into a single string for CLI adapters."""
    if system_prompt:
        return f"{system_prompt}\n\n---\n\n{prompt}"
    return prompt
