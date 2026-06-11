"""Claude CLI runtime adapter — second profile (claude-work).

Uses the Claude Code CLI binary with a separate --data-dir so it runs
a different account/profile than the default ~/.claude adapter.

Set CLAUDE_WORK_DATA_DIR in backend/.env to override the profile path
(default: ~/.claude-work).
"""

import json
import os
import shutil
from pathlib import Path

from app.services.runtime._utils import combine_prompts
from app.services.runtime.cli_exec import CLI_BRIDGE_URL, run_command

BINARY = "claude"
TIMEOUT_SECONDS = 300
_DEFAULT_DATA_DIR = str(Path.home() / ".claude-work")


def _data_dir() -> str:
    return os.environ.get("CLAUDE_WORK_DATA_DIR", _DEFAULT_DATA_DIR)


async def run_agent(
    *,
    prompt: str,
    system_prompt: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, dict]:
    """Invoke claude --data-dir <work-profile> --print --output-format json."""
    data_dir = _data_dir()

    if not CLI_BRIDGE_URL and not shutil.which(BINARY):
        raise RuntimeError(
            "claude binary not found on PATH — install Claude Code CLI or start the CLI bridge"
        )

    if not Path(data_dir).exists():
        raise RuntimeError(
            f"Claude work profile directory not found: {data_dir} — "
            "set CLAUDE_WORK_DATA_DIR in backend/.env to the correct path"
        )

    full_prompt = combine_prompts(system_prompt, prompt)
    args = [BINARY, "--data-dir", data_dir, "--print", "--output-format", "json", "--dangerously-skip-permissions"]
    if model:
        args += ["--model", model]
    args.append(full_prompt)

    result = await run_command(args, timeout=TIMEOUT_SECONDS)

    out = result.stdout.strip()
    err = result.stderr.strip()

    if result.returncode != 0:
        return (
            f"[claude-cli-work error (exit {result.returncode}): {err or out or 'unknown error'}]",
            {"runtime": "claude-cli-work", "available": True, "tokens_used": None},
        )

    text, tokens = _parse_output(out)
    return text, {
        "runtime": "claude-cli-work",
        "available": True,
        "model": model,
        "tokens_used": tokens,
        "data_dir": data_dir,
    }


def _parse_output(out: str) -> tuple[str, int | None]:
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
    data_dir = _data_dir()
    dir_exists = Path(data_dir).exists()
    if CLI_BRIDGE_URL:
        return {
            "kind": "claude-cli-work",
            "available": dir_exists,
            "detail": f"via CLI bridge at {CLI_BRIDGE_URL}, data_dir={data_dir} ({'exists' if dir_exists else 'MISSING'})",
        }
    binary = shutil.which(BINARY)
    available = binary is not None and dir_exists
    return {
        "kind": "claude-cli-work",
        "available": available,
        "detail": (
            f"found at {binary}, data_dir={data_dir}"
            if available
            else f"binary={binary or 'NOT FOUND'}, data_dir={data_dir} ({'exists' if dir_exists else 'MISSING'})"
        ),
    }
