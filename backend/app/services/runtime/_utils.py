"""Shared helpers for CLI runtime adapters."""


def combine_prompts(system_prompt: str, prompt: str) -> str:
    """Merge system prompt and user prompt into a single string for CLI adapters."""
    if system_prompt:
        return f"{system_prompt}\n\n---\n\n{prompt}"
    return prompt
