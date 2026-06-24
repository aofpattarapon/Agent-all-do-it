"""Model fallback — retries a failing LLM call through a provider chain.

If the primary runtime adapter fails (network error, quota, outage), this
service automatically tries the next adapter in the chain before giving up.

Usage (replaces bare ``runtime.run_agent()`` in RunExecutor):
    output, meta = await run_with_fallback(agent, prompt=prompt, system_prompt=system_prompt)
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

from app.services import runtime as runtime_mod
from app.services.llm_error_classifier import classify_llm_error

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.project import AgentConfig

logger = logging.getLogger(__name__)

# Roles whose prompts explicitly request JSON output.  When the primary/fallback
# adapter is Ollama, request structured JSON mode so local models are less likely
# to emit prose or markdown-wrapped payloads.
_JSON_EMITTING_ROLES: frozenset[str] = frozenset({
    "hawk_trend",
    "hawk_structure",
    "hawk_counter",
    "sage",
    "trade_proposal",
    "execution",
    "market_regime",
    "source_reliability",
    "news_monitor",
    "position_monitor",
    "trade_journal",
    "post_trade_review",
})

# Ordered fallback chains: primary → fallback1 → fallback2
# CLI adapters fall back to their API equivalent, then to a cheap API model.
FALLBACK_CHAIN: dict[str, list[str]] = {
    "claude-cli": ["claude-cli-work", "anthropic-api", "groq-api", "openai-api"],
    "codex-cli": ["openai-api", "groq-api", "anthropic-api"],
    "kimi-cli": ["openrouter-api", "groq-api", "anthropic-api"],
    "kimi-api": ["openrouter-api", "openrouter-api", "groq-api", "openai-api", "anthropic-api"],
    "groq-api": ["cerebras-api", "openrouter-api", "anthropic-api", "openai-api"],
    "cerebras-api": ["groq-api", "openrouter-api", "anthropic-api", "openai-api"],
    "google-ai-studio": ["groq-api", "cerebras-api", "openrouter-api", "anthropic-api"],
    "anthropic-api": ["groq-api", "openai-api"],
    "openai-api": ["groq-api", "anthropic-api"],
    "ollama": ["groq-api", "anthropic-api", "openai-api"],
    "openrouter-api": ["kimi-api", "groq-api", "anthropic-api", "openai-api"],
}

_UNRECOVERABLE = {"context_limit_exceeded"}
_SKIP_ADAPTER = {"auth_error"}  # bad key on this adapter — skip it, still try next

# When falling back to a different adapter family, substitute a valid default model.
# The agent's configured model (e.g. "kimi-k2.6") only exists on its own provider.
# openrouter-api entry is a dict: primary-specific overrides + "default" fallback.
# Values may be:
#   str                      — single model for all attempts
#   dict[str, str|list[str]] — per-primary override; list = cycle through on repeated attempts
_DEFAULT_MODELS: dict[str, str | dict[str, str | list[str]]] = {
    "groq-api": "llama-3.3-70b-versatile",
    "cerebras-api": "llama-3.3-70b",
    "google-ai-studio": "gemini-2.0-flash",
    "anthropic-api": "claude-haiku-4-5-20251001",
    "openai-api": "gpt-4o-mini",
    "openrouter-api": {
        "kimi-api": ["moonshotai/kimi-k2", "openai/gpt-oss-120b:free"],
        "kimi-cli": ["moonshotai/kimi-k2", "openai/gpt-oss-120b:free"],
        "default": "openai/gpt-oss-120b:free",
    },
    "kimi-api": "moonshot-v1-8k",
    "ollama": "llama3",
}

# RPM-spike protection: if Retry-After ≤ this, wait and retry the SAME adapter.
_MAX_INLINE_WAIT_SECS = 35
# How many times to retry the same adapter on a short 429 before moving on.
_MAX_SAME_ADAPTER_RETRIES = 2
# Random jitter added before each cross-adapter fallback to spread concurrent calls.
_JITTER_SECS = (0.5, 2.5)
# Upper bound for the exponential backoff applied to a 429 that carries no usable
# Retry-After header (Groq/Cerebras/Gemini commonly omit it). Keeps a free-tier RPM
# burst queued on the same adapter instead of cascading every agent onto OpenRouter.
_MAX_BACKOFF_SECS = 8


def _extract_retry_after(exc: Exception) -> int | None:
    """Read Retry-After seconds from an httpx/openai SDK exception's response headers."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", {}) or {}
    val = headers.get("retry-after") or headers.get("Retry-After")
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


async def run_with_fallback(
    agent: AgentConfig,
    *,
    prompt: str,
    system_prompt: str = "",
    db: AsyncSession | None = None,
) -> tuple[str, dict]:
    """Run ``agent`` with automatic fallback on transient failures.

    Tries the agent's configured runtime first, then each adapter in its
    FALLBACK_CHAIN. For short 429 rate-limit responses (Retry-After ≤ 35s),
    waits and retries the same adapter before moving on. Adds random jitter
    before each cross-adapter transition to prevent concurrent RPM spikes.

    Pass ``db`` so that API keys and URLs saved via the admin UI are used
    instead of requiring a container restart to pick up env var changes.
    """
    primary = (getattr(agent, "runtime_kind", "") or "anthropic-api").strip()

    # Prefer per-agent stored fallback chain (set by apply-runtime-profile command).
    # Each entry is {"runtime_kind": "...", "model": "..."} — we extract kinds for the chain.
    _stored_chain: list[dict] = (getattr(agent, "tools_config", None) or {}).get(
        "fallback_chain"
    ) or []
    if _stored_chain:
        chain = [
            primary,
            *[
                e["runtime_kind"]
                for e in _stored_chain
                if isinstance(e, dict) and e.get("runtime_kind")
            ],
        ]
    else:
        chain = [primary, *FALLBACK_CHAIN.get(primary, [])]

    # Load DB-stored config once up front (avoids N queries for an N-step fallback chain).
    ai_config: dict | None = None
    if db is not None:
        try:
            from app.services.app_setting import AppSettingService

            ai_config = await AppSettingService(db).get_ai_config()
        except Exception as exc:
            logger.warning("Could not load AI config from DB, falling back to env vars: %s", exc)

    last_exc: Exception | None = None
    primary_exc: Exception | None = None
    adapter_seen: dict[str, int] = {}  # counts how many times each adapter has been tried

    for attempt, kind in enumerate(chain):
        adapter = runtime_mod._ADAPTERS.get(kind)
        if adapter is None:
            logger.warning(
                "Fallback: unknown/unregistered adapter '%s' in chain — skipping "
                "(this silently shortens the fallback chain; check the stored runtime_kind)",
                kind,
            )
            continue

        agent_model = getattr(agent, "model", "") or ""
        # When switching adapter families, substitute a provider-compatible default model.
        kind_attempt = adapter_seen.get(kind, 0)
        adapter_seen[kind] = kind_attempt + 1

        if kind == primary:
            model = agent_model
        else:
            # Check per-agent stored chain first for an explicit model override.
            stored_model: str | None = None
            if _stored_chain:
                for entry in _stored_chain:
                    if isinstance(entry, dict) and entry.get("runtime_kind") == kind:
                        stored_model = entry.get("model") or None
                        break
            if stored_model:
                model = stored_model
            else:
                default = _DEFAULT_MODELS.get(kind)
                if isinstance(default, dict):
                    per_primary = default.get(primary) or default.get("default") or agent_model
                    if isinstance(per_primary, list):
                        model = per_primary[min(kind_attempt, len(per_primary) - 1)]
                    else:
                        model = per_primary
                else:
                    model = default or agent_model
        max_tokens = getattr(agent, "max_tokens", None) or 2048
        raw_temp = getattr(agent, "temperature", None)
        temperature = (
            (raw_temp / 100.0)
            if isinstance(raw_temp, int) and not isinstance(raw_temp, bool)
            else (raw_temp if isinstance(raw_temp, float) else 0.7)
        )

        agent_role = (getattr(agent, "role", "") or "").strip()

        # Inject DB-stored credentials/URLs for adapters that need them.
        extra: dict = {}
        if ai_config is not None:
            if kind == "kimi-api":
                extra["api_key"] = ai_config.get("moonshot_api_key") or None
            elif kind == "groq-api":
                extra["api_key"] = ai_config.get("groq_api_key") or None
            elif kind == "cerebras-api":
                extra["api_key"] = ai_config.get("cerebras_api_key") or None
            elif kind == "google-ai-studio":
                extra["api_key"] = ai_config.get("google_api_key") or None
            elif kind == "openrouter-api":
                extra["api_key"] = ai_config.get("openrouter_api_key") or None
            elif kind == "ollama":
                extra["base_url"] = ai_config.get("ollama_url") or None
                if agent_role in _JSON_EMITTING_ROLES:
                    extra["format"] = "json"

        # ── Inner retry loop: retry the same adapter on short 429s ──────────
        same_adapter_retries = 0
        while True:
            try:
                output, meta = await adapter.run_agent(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **extra,
                )
                if attempt > 0 or same_adapter_retries > 0:
                    logger.info(
                        "Fallback succeeded on adapter '%s' (primary was '%s', same-adapter retries: %d)",
                        kind,
                        primary,
                        same_adapter_retries,
                    )
                    meta["fallback_used"] = True
                    meta["fallback_from"] = primary
                return output, meta

            except Exception as exc:
                last_exc = exc
                if attempt == 0 and same_adapter_retries == 0:
                    primary_exc = exc
                info = classify_llm_error(exc)
                logger.warning("Adapter '%s' failed (%s): %s", kind, info.error_type, exc)

                if info.error_type in _UNRECOVERABLE:
                    logger.warning(
                        "Unrecoverable error type '%s' — aborting fallback chain", info.error_type
                    )
                    primary_msg = (
                        f" ({primary_exc})" if primary_exc and primary_exc is not last_exc else ""
                    )
                    raise RuntimeError(
                        f"Agent runtime '{primary}' failed{primary_msg}. "
                        f"Unrecoverable error: {last_exc}"
                    ) from last_exc

                if info.error_type in _SKIP_ADAPTER:
                    logger.warning(
                        "Auth error on '%s' — skipping this adapter, trying next in chain", kind
                    )
                    break  # exit inner loop → next adapter

                # 429: wait and retry the same adapter before giving up on it.
                # Honour a short Retry-After header when present; otherwise back off
                # exponentially so a header-less RPM burst queues instead of cascading.
                if (
                    info.error_type == "rate_limited"
                    and same_adapter_retries < _MAX_SAME_ADAPTER_RETRIES
                ):
                    retry_after = _extract_retry_after(exc)
                    jitter = random.uniform(*_JITTER_SECS)
                    if retry_after is not None and 0 < retry_after <= _MAX_INLINE_WAIT_SECS:
                        wait = retry_after + jitter
                        logger.info(
                            "Adapter '%s' rate-limited (Retry-After: %ds) — waiting %.1fs then retrying same adapter (attempt %d/%d)",
                            kind,
                            retry_after,
                            wait,
                            same_adapter_retries + 1,
                            _MAX_SAME_ADAPTER_RETRIES,
                        )
                        await asyncio.sleep(wait)
                        same_adapter_retries += 1
                        continue  # retry same adapter
                    if retry_after is None or retry_after > _MAX_INLINE_WAIT_SECS:
                        backoff = min(2**same_adapter_retries, _MAX_BACKOFF_SECS)
                        wait = backoff + jitter
                        logger.info(
                            "Adapter '%s' rate-limited (no usable Retry-After) — backing off %.1fs then retrying same adapter (attempt %d/%d)",
                            kind,
                            wait,
                            same_adapter_retries + 1,
                            _MAX_SAME_ADAPTER_RETRIES,
                        )
                        await asyncio.sleep(wait)
                        same_adapter_retries += 1
                        continue  # retry same adapter

                # Moving to next adapter — add jitter to spread concurrent agent calls.
                if attempt < len(chain) - 1:
                    jitter = random.uniform(*_JITTER_SECS)
                    logger.debug(
                        "Jitter %.1fs before falling back from '%s' to next adapter", jitter, kind
                    )
                    await asyncio.sleep(jitter)
                break  # exit inner loop → next adapter

    primary_msg = f" ({primary_exc})" if primary_exc and primary_exc is not last_exc else ""
    raise RuntimeError(
        f"Agent runtime '{primary}' failed{primary_msg}. "
        f"All fallback adapters also failed. Last error: {last_exc}"
    ) from last_exc
