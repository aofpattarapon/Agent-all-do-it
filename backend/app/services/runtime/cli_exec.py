"""Shared CLI execution helper.

When running inside Docker, Mac binaries can't be executed directly.
If CLI_BRIDGE_URL is set, all CLI calls are proxied to the bridge server
running on the host Mac (backend/cli/bridge_server.py).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

CLI_BRIDGE_URL = os.environ.get("CLI_BRIDGE_URL", "").rstrip("/")


@dataclass
class ExecResult:
    returncode: int
    stdout: str
    stderr: str


async def run_command(args: list[str], timeout: int = 300) -> ExecResult:
    """Run a CLI command, routing through the bridge if CLI_BRIDGE_URL is set."""
    if CLI_BRIDGE_URL:
        return await _bridge_exec(args, timeout)
    return await _local_exec(args, timeout)


async def _local_exec(args: list[str], timeout: int) -> ExecResult:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        return ExecResult(-1, "", f"timed out after {timeout}s")
    return ExecResult(
        proc.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def _bridge_exec(args: list[str], timeout: int) -> ExecResult:
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{CLI_BRIDGE_URL}/exec",
                json={"args": args, "timeout": timeout},
                timeout=timeout + 10,
            )
            resp.raise_for_status()
            data = resp.json()
        return ExecResult(data["returncode"], data.get("stdout", ""), data.get("stderr", ""))
    except Exception as exc:
        raise RuntimeError(
            f"CLI bridge unreachable at {CLI_BRIDGE_URL} — "
            f"start backend/cli/bridge_server.py on your Mac: {exc}"
        ) from exc
