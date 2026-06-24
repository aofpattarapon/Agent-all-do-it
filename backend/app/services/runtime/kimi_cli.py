"""Kimi CLI runtime adapter — drives the local ``kimi`` binary.

Two binaries may be available:

1. **Official Kimi Code CLI** (``~/.kimi-code/bin/kimi``) — behaves like
   Claude CLI / Codex CLI. Uses subscription auth, no API key needed.
   Args: ``kimi -p "<prompt>" [-m "<model>"]``

2. **Project wrapper** (``backend/cli/kimi``) — direct Moonshot REST API call.
   Needs a Moonshot API key in ``~/.config/kimi/api_key``.
   Args: ``kimi chat "<prompt>" [--model "<model>"]``

The adapter auto-detects which binary is present and formats args accordingly.
"""

import shutil

from app.services.runtime._utils import combine_prompts
from app.services.runtime.cli_exec import CLI_BRIDGE_URL, run_command

TIMEOUT_SECONDS = 300

_binary_type_cache: str | None = None


async def _detect_binary_type() -> str:
    """Return 'official' or 'wrapper' depending on which binary is available."""
    global _binary_type_cache
    if _binary_type_cache is not None:
        return _binary_type_cache

    if CLI_BRIDGE_URL:
        # When running via the bridge (Docker → host Mac), the bridge always
        # exposes the official Kimi Code CLI. Never fall back to "wrapper" here —
        # a failed /which call would cache "wrapper" permanently and cause
        # kimi 0.8.0 to receive "kimi chat <prompt>" which is not a valid command.
        _binary_type_cache = "official"
        return _binary_type_cache

    # Local mode: check PATH directly
    found = shutil.which("kimi") or ""
    if "kimi-code" in found:
        _binary_type_cache = "official"
    else:
        _binary_type_cache = "wrapper"
    return _binary_type_cache


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, dict]:
    """Invoke the best available ``kimi`` binary (official CLI or wrapper)."""
    binary_type = await _detect_binary_type()
    binary = "kimi"  # the bridge or local PATH resolves the actual path

    full_prompt = combine_prompts(system_prompt, prompt)

    if binary_type == "official":
        # Official Kimi Code CLI: kimi -p "prompt"
        # Always use config.toml default model — the official CLI only has
        # one configured model (kimi-code/kimi-for-coding) and will error on
        # any other model string (moonshotai/kimi-k2, kimi-k2.6, etc.)
        args = [binary, "-p", full_prompt]
    else:
        # Project wrapper: kimi chat "prompt" [--model "model"]
        args = [binary, "chat", full_prompt]
        if model:
            args += ["--model", model]

    result = await run_command(args, timeout=TIMEOUT_SECONDS)

    out = result.stdout.strip()
    err = result.stderr.strip()

    if result.returncode != 0:
        return (
            f"[kimi-cli error (exit {result.returncode}): {err or out or 'unknown error'}]",
            {"runtime": "kimi-cli", "available": True, "tokens_used": None},
        )

    return out, {"runtime": "kimi-cli", "available": True, "model": model, "tokens_used": None}


def healthcheck() -> dict:
    """Check whether a ``kimi`` binary is available."""
    if CLI_BRIDGE_URL:
        return {
            "kind": "kimi-cli",
            "available": True,
            "detail": f"via CLI bridge at {CLI_BRIDGE_URL}",
        }
    found = shutil.which("kimi")
    if found:
        kind = "official" if "kimi-code" in found else "wrapper"
        return {"kind": "kimi-cli", "available": True, "detail": f"{kind} at {found}"}
    return {
        "kind": "kimi-cli",
        "available": False,
        "detail": "'kimi' not found on PATH — install Kimi Code CLI or place backend/cli/kimi on PATH",
    }
