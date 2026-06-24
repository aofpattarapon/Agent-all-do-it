"""Claude CLI runtime adapter — drives the local ``claude`` binary.

Runs an agent WITHOUT an API key by shelling out to the user's installed
Claude Code CLI. When CLI_BRIDGE_URL is set (Docker), calls are proxied
to the bridge server running on the host Mac.
"""

import json
import shutil

from app.services.runtime._utils import combine_prompts
from app.services.runtime.cli_exec import CLI_BRIDGE_URL, run_command

BINARY = "claude"
TIMEOUT_SECONDS = 300


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, dict]:
    """Invoke ``claude --print --output-format json`` via local binary or CLI bridge."""
    if not CLI_BRIDGE_URL and not shutil.which(BINARY):
        raise RuntimeError(
            "claude binary not found on PATH — install Claude Code CLI or start the CLI bridge"
        )

    full_prompt = combine_prompts(system_prompt, prompt)
    args = [BINARY, "--print", "--output-format", "json", "--dangerously-skip-permissions"]
    if model:
        args += ["--model", model]
    args.append(full_prompt)

    result = await run_command(args, timeout=TIMEOUT_SECONDS)

    out = result.stdout.strip()
    err = result.stderr.strip()

    if result.returncode != 0:
        return (
            f"[claude-cli error (exit {result.returncode}): {err or out or 'unknown error'}]",
            {"runtime": "claude-cli", "available": True, "tokens_used": None},
        )

    text, tokens = _parse_output(out)
    return text, {"runtime": "claude-cli", "available": True, "model": model, "tokens_used": tokens}


def _parse_output(out: str) -> tuple[str, int | None]:
    """Parse ``claude --output-format json`` stdout."""
    if not out:
        return "", None
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return out, None

    if isinstance(data, dict):
        text = data.get("result") or data.get("text") or data.get("content") or ""
        if isinstance(text, list):
            text = "".join(b.get("text", "") for b in text if isinstance(b, dict))
        tokens = None
        usage = data.get("usage")
        if isinstance(usage, dict):
            tokens = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0) or None
        return str(text), tokens
    return out, None


def healthcheck() -> dict:
    """Check whether the ``claude`` binary is on PATH (or bridge is configured)."""
    if CLI_BRIDGE_URL:
        return {
            "kind": "claude-cli",
            "available": True,
            "detail": f"via CLI bridge at {CLI_BRIDGE_URL}",
        }
    binary = shutil.which(BINARY)
    return {
        "kind": "claude-cli",
        "available": binary is not None,
        "detail": f"found at {binary}" if binary else "'claude' binary not found on PATH",
    }
