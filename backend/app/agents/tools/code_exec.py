"""Code execution tool for agents.

SANDBOX NOTE: This is NOT a real sandbox. Code runs in a subprocess on the
host with a timeout and a tiny denylist of obviously dangerous patterns. It is
suitable for development only. Do NOT expose this to untrusted input in
production without a proper isolation layer (container / gVisor / firejail / etc).
"""

import asyncio
import logging
import sys

logger = logging.getLogger(__name__)

# Crude denylist of obviously dangerous patterns. NOT exhaustive — see module
# docstring. Matched as plain substrings, case-sensitive.
_DENYLIST = (
    "os.system",
    "subprocess",
    "shutil.rmtree",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "__import__",
)


def _denied(code: str) -> str | None:
    """Return the first denied pattern found in ``code``, else None."""
    for pattern in _DENYLIST:
        if pattern in code:
            return pattern
    return None


async def execute_code(code: str, language: str = "python", timeout: int = 10) -> dict:
    """Execute a snippet of code in a subprocess with a timeout.

    Args:
        code: Source code to run.
        language: Currently only ``"python"`` is supported.
        timeout: Wall-clock timeout in seconds.

    Returns:
        A dict with ``stdout``, ``stderr`` and ``exit_code``.
    """
    if language != "python":
        return {
            "stdout": "",
            "stderr": f"Unsupported language: {language!r} (only 'python' is supported)",
            "exit_code": -1,
        }

    blocked = _denied(code)
    if blocked is not None:
        return {
            "stdout": "",
            "stderr": f"Blocked: code contains a disallowed pattern ({blocked!r})",
            "exit_code": -1,
        }

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as exc:  # noqa: BLE001 - never raise from a tool
        logger.warning("code_exec failed to start subprocess: %s", exc)
        return {"stdout": "", "stderr": f"Failed to start subprocess: {exc}", "exit_code": -1}

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return {"stdout": "", "stderr": f"Execution timed out after {timeout}s", "exit_code": -1}

    return {
        "stdout": stdout_b.decode("utf-8", errors="replace"),
        "stderr": stderr_b.decode("utf-8", errors="replace"),
        "exit_code": proc.returncode if proc.returncode is not None else -1,
    }
