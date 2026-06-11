"""Claude Code SDK service.

Supports two backends per agent (configured via AgentConfig.tools_config):
  - "claude-cli"  : uses claude-code-sdk → local CLI → subscription billing
  - "anthropic-api": uses langchain-anthropic → direct API → pay-per-token

Default is "claude-cli". Falls back to "anthropic-api" automatically when
the CLI is not reachable (e.g. binary not mounted into container).
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)

BACKEND_CLI = "claude-cli"
BACKEND_API = "anthropic-api"


@dataclass
class AgentResult:
    text: str
    cost_usd: float | None = None
    is_error: bool = False
    error_message: str | None = None
    backend: str = "unknown"


@dataclass
class AgentEvent:
    type: str   # "text" | "result" | "error"
    data: str
    cost_usd: float | None = None
    backend: str = "unknown"


async def _stream_cli(prompt: str, system_prompt: str, max_turns: int) -> AsyncIterator[AgentEvent]:
    """Stream via Claude CLI subprocess — bypasses SDK message-type limitations.

    Calls `claude` binary directly with --print flag and captures stdout.
    This avoids SDK issues with unknown message types like rate_limit_event.
    """
    import asyncio
    import shutil

    cli_path = shutil.which("claude")
    if not cli_path:
        return "[claude-cli error: 'claude' binary not found on PATH. Install Claude Code CLI.]"

    cmd = [
        cli_path,
        "--print",
        "--output-format", "text",
        "--max-turns", str(max_turns),
        "--system-prompt", system_prompt,
        prompt,
    ]

    logger.info("Running Claude CLI: %s", cli_path)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        logger.warning("Claude CLI exit %d: %s", proc.returncode, err[:200])
        raise RuntimeError(f"Claude CLI error (exit {proc.returncode}): {err[:200]}")

    text = stdout.decode(errors="replace").strip()
    if text:
        yield AgentEvent(type="text", data=text, backend=BACKEND_CLI)
    yield AgentEvent(type="result", data="", backend=BACKEND_CLI)


async def _stream_api(prompt: str, system_prompt: str, model: str, api_key: str = "") -> AsyncIterator[AgentEvent]:
    """Stream via langchain-anthropic (direct Anthropic API)."""
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.core.config import settings

    # DB-stored key (from app_settings) takes precedence over .env
    resolved_key = api_key or settings.ANTHROPIC_API_KEY
    if not resolved_key:
        yield AgentEvent(type="error", data="ANTHROPIC_API_KEY not configured. Go to Settings → AI Backend to set it.", backend=BACKEND_API)
        return

    llm = ChatAnthropic(
        model=model,
        anthropic_api_key=resolved_key,
        max_tokens=4096,
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]
    async for chunk in llm.astream(messages):
        if chunk.content:
            text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
            yield AgentEvent(type="text", data=text, backend=BACKEND_API)
    yield AgentEvent(type="result", data="", backend=BACKEND_API)


class ClaudeCodeService:
    """Run an agent with a configurable backend.

    tools_config options (stored in AgentConfig.tools_config):
      ai_backend: "claude-cli" | "anthropic-api"  (default: "claude-cli")
      model: str  (default: "claude-haiku-4-5-20251001", used by anthropic-api only)
      auto_fallback: true | false  (default: true — fall back to api if cli fails)
    """

    async def stream(
        self,
        prompt: str,
        system_prompt: str,
        max_turns: int = 10,
        tools_config: dict | None = None,
    ) -> AsyncIterator[AgentEvent]:
        cfg = tools_config or {}
        backend = cfg.get("ai_backend", BACKEND_CLI)
        model = cfg.get("model", "claude-haiku-4-5-20251001")
        auto_fallback = cfg.get("auto_fallback", True)
        injected_api_key = cfg.get("_anthropic_api_key", "")

        if backend == BACKEND_CLI:
            try:
                has_output = False
                async for event in _stream_cli(prompt, system_prompt, max_turns):
                    if event.type == "text" and event.data:
                        has_output = True
                    yield event
                if has_output:
                    return
                # CLI ran but produced no text — might still be valid (empty response)
                # Only fall through if we got zero events at all
            except ImportError:
                logger.debug("claude-code-sdk not installed")
            except Exception as exc:
                # "Unknown message type" errors from SDK are non-fatal — keep going
                if "Unknown message type" in str(exc):
                    logger.debug("claude-code-sdk unknown message skipped: %s", exc)
                    return  # whatever came before was already yielded
                logger.warning("Claude CLI failed: %s", exc)

            if not auto_fallback:
                yield AgentEvent(type="error", data="Claude CLI unavailable and auto_fallback is disabled", backend=BACKEND_CLI)
                return

            logger.info("Falling back to anthropic-api")
            backend = BACKEND_API

        # anthropic-api backend (pass DB-injected API key)
        async for event in _stream_api(prompt, system_prompt, model, api_key=injected_api_key):
            yield event

    async def run(
        self,
        prompt: str,
        system_prompt: str,
        max_turns: int = 10,
        tools_config: dict | None = None,
    ) -> AgentResult:
        parts: list[str] = []
        cost: float | None = None
        used_backend = "unknown"

        async for event in self.stream(
            prompt=prompt,
            system_prompt=system_prompt,
            max_turns=max_turns,
            tools_config=tools_config,
        ):
            if event.type == "text":
                parts.append(event.data)
                used_backend = event.backend
            elif event.type == "result":
                cost = event.cost_usd
                used_backend = event.backend
            elif event.type == "error":
                return AgentResult(text="", is_error=True, error_message=event.data, backend=event.backend)

        return AgentResult(text="".join(parts), cost_usd=cost, backend=used_backend)
