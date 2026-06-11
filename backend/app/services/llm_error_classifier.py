"""LLM error classifier (ported from SDLC RecoveryWorker).

Inspects an exception or error message and decides whether a run should be
*paused* (and auto-resumed later) or *failed*. Quota / rate-limit / transient
provider errors are pausable; auth errors require a manual token fix.
"""

import re
from dataclasses import dataclass


@dataclass
class LLMErrorInfo:
    is_quota_error: bool
    error_type: str  # quota_exceeded|rate_limited|context_limit_exceeded|provider_unavailable|auth_error|timeout|unknown_llm_error|transient
    http_status: int
    retry_after_seconds: int
    resume_policy: str  # auto | manual_token_fix
    provider_hint: str
    raw_message: str

    @property
    def should_pause(self) -> bool:
        return self.is_quota_error


# ── Rule definitions (ordered: first match wins) ───────────────────────────────
# Each rule: (error_type, regex, http_status, retry_after_seconds, resume_policy, is_quota)
_RULES: list[tuple[str, re.Pattern[str], int, int, str, bool]] = [
    (
        "auth_error",
        re.compile(r"\b(401|403)\b|invalid[\s_-]?(api[\s_-]?)?key|unauthorized|authentication[\s_-]?fail|"
                   r"permission[\s_-]?denied|invalid[\s_-]?x[\s_-]?api[\s_-]?key|not[\s_-]?configured", re.I),
        401, 0, "manual_token_fix", True,
    ),
    (
        "quota_exceeded",
        re.compile(r"quota|billing|insufficient[\s_-]?(funds|credit|balance)|"
                   r"credit[\s_-]?balance[\s_-]?(is[\s_-]?)?too[\s_-]?low|exceeded[\s_-]?your[\s_-]?current", re.I),
        429, 3600, "auto", True,
    ),
    (
        "rate_limited",
        re.compile(r"\b429\b|rate[\s_-]?limit|too[\s_-]?many[\s_-]?requests|slow[\s_-]?down", re.I),
        429, 60, "auto", True,
    ),
    (
        "context_limit_exceeded",
        re.compile(r"context[\s_-]?(length|window)|maximum[\s_-]?context|too[\s_-]?(long|large|many[\s_-]?tokens)|"
                   r"prompt[\s_-]?is[\s_-]?too[\s_-]?long|input[\s_-]?too[\s_-]?long", re.I),
        400, 0, "auto", True,
    ),
    (
        "provider_unavailable",
        re.compile(r"\b(500|502|503|504)\b|overloaded|service[\s_-]?unavailable|"
                   r"internal[\s_-]?server[\s_-]?error|bad[\s_-]?gateway|gateway[\s_-]?timeout|"
                   r"server[\s_-]?(is[\s_-]?)?busy|capacity", re.I),
        503, 120, "auto", True,
    ),
    (
        "timeout",
        re.compile(r"\btimed?[\s_-]?out\b|timeout|deadline[\s_-]?exceeded|read[\s_-]?timeout|connect[\s_-]?timeout", re.I),
        408, 30, "auto", True,
    ),
]

_PROVIDER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic", re.compile(r"anthropic|claude", re.I)),
    ("openai", re.compile(r"openai|gpt", re.I)),
    ("ollama", re.compile(r"ollama|llama", re.I)),
    ("google", re.compile(r"google|gemini", re.I)),
]

_STATUS_PATTERN = re.compile(r"\b(4\d{2}|5\d{2})\b")


def _extract_message(exc_or_message: object) -> str:
    if isinstance(exc_or_message, BaseException):
        # Prefer a status_code attribute if the SDK exposes one (httpx/anthropic).
        parts = [str(exc_or_message)]
        status = getattr(exc_or_message, "status_code", None)
        if status is not None:
            parts.append(f"status {status}")
        return " ".join(parts)
    return str(exc_or_message or "")


def _detect_provider(message: str) -> str:
    for name, pattern in _PROVIDER_PATTERNS:
        if pattern.search(message):
            return name
    return ""


def _detect_status(message: str, fallback: int) -> int:
    match = _STATUS_PATTERN.search(message)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return fallback


def classify_llm_error(exc_or_message: object) -> LLMErrorInfo:
    """Classify an exception or error string into an :class:`LLMErrorInfo`.

    Returns a non-quota ``unknown_llm_error`` when nothing matches.
    """
    message = _extract_message(exc_or_message)
    provider = _detect_provider(message)

    for error_type, pattern, http_status, retry_after, resume_policy, is_quota in _RULES:
        if pattern.search(message):
            return LLMErrorInfo(
                is_quota_error=is_quota,
                error_type=error_type,
                http_status=_detect_status(message, http_status),
                retry_after_seconds=retry_after,
                resume_policy=resume_policy,
                provider_hint=provider,
                raw_message=message[:2000],
            )

    return LLMErrorInfo(
        is_quota_error=False,
        error_type="unknown_llm_error",
        http_status=_detect_status(message, 0),
        retry_after_seconds=0,
        resume_policy="auto",
        provider_hint=provider,
        raw_message=message[:2000],
    )
