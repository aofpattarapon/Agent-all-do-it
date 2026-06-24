"""Codex CLI runtime adapter — drives the local ``codex`` binary."""

import json
import shutil

from app.services.runtime._utils import combine_prompts
from app.services.runtime.cli_exec import CLI_BRIDGE_URL, run_command

BINARY = "codex"
TIMEOUT_SECONDS = 300


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, dict]:
    """Invoke ``codex exec`` with the combined prompt via local binary or CLI bridge."""
    if not CLI_BRIDGE_URL and not shutil.which(BINARY):
        raise RuntimeError(
            "codex binary not found on PATH — install the Codex CLI or switch the agent runtime to openai-api"
        )

    full_prompt = combine_prompts(system_prompt, prompt)
    # --skip-git-repo-check: required when not in a trusted git directory
    # --full-auto: non-interactive, no stdin prompts
    args = [BINARY, "exec", "--skip-git-repo-check", "--full-auto"]
    if model:
        args += ["--model", model]
    args.append(full_prompt)

    result = await run_command(args, timeout=TIMEOUT_SECONDS)

    out = result.stdout.strip()
    err = result.stderr.strip()

    if result.returncode != 0:
        return (
            f"[codex-cli error (exit {result.returncode}): {err or out or 'unknown error'}]",
            {"runtime": "codex-cli", "available": True, "tokens_used": None},
        )

    text = _parse_output(out)
    return text, {"runtime": "codex-cli", "available": True, "model": model, "tokens_used": None}


def _parse_output(out: str) -> str:
    """Codex ``exec`` prints plain text; try JSON first, fall back to raw."""
    if not out:
        return ""
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return out
    if isinstance(data, dict):
        return str(data.get("result") or data.get("text") or data.get("content") or out)
    return out


def healthcheck() -> dict:
    """Check whether the ``codex`` binary is on PATH (or bridge is configured)."""
    if CLI_BRIDGE_URL:
        return {
            "kind": "codex-cli",
            "available": True,
            "detail": f"via CLI bridge at {CLI_BRIDGE_URL}",
        }
    binary = shutil.which(BINARY)
    return {
        "kind": "codex-cli",
        "available": binary is not None,
        "detail": f"found at {binary}" if binary else "'codex' binary not found on PATH",
    }
