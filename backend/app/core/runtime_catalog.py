"""Authoritative runtime/model compatibility rules."""

from __future__ import annotations

from app.core.exceptions import ValidationError

DEFAULT_MODEL_VALUE = "__default__"

RUNTIME_MODEL_OPTIONS: dict[str, list[str]] = {
    "claude-cli": [
        "",
        "claude-sonnet-4-6",
        "claude-opus-4-8",
        "claude-haiku-4-5-20251001",
        "claude-fable-5",
    ],
    "codex-cli": [
        "",
        "o4-mini",
        "gpt-5.4",
    ],
    "kimi-cli": [
        "",
        "kimi-k2.6",
        "kimi-k2.5",
        "moonshot-v1-8k",
    ],
    "kimi-api": [
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
        "moonshot-v1-auto",
        "kimi-k2.6",
        "kimi-k2.5",
    ],
    "groq-api": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    "cerebras-api": [
        "llama-3.3-70b",
        "llama-3.1-8b",
        "qwen-3-32b",
    ],
    "google-ai-studio": [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
    ],
    "anthropic-api": [
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6",
        "claude-opus-4-8",
        "claude-fable-5",
    ],
    "openai-api": [
        "gpt-4o",
        "gpt-5.4",
        "o4-mini",
        "o3",
    ],
    "ollama": [
        "",
        "llama3.1",
        "mistral",
        "codellama",
        "qwen3:8b",
        "qwen3:14b",
        "gemma3:12b",
    ],
    "openrouter-api": [
        "openai/gpt-oss-120b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "openrouter/owl-alpha",
    ],
}

DEFAULT_MODEL_BY_RUNTIME: dict[str, str] = {
    "claude-cli": "",
    "codex-cli": "",
    "kimi-cli": "",
    "kimi-api": "moonshot-v1-8k",
    "groq-api": "llama-3.3-70b-versatile",
    "cerebras-api": "llama-3.3-70b",
    "google-ai-studio": "gemini-2.0-flash",
    "anthropic-api": "claude-haiku-4-5-20251001",
    "openai-api": "gpt-4o",
    "ollama": "",
    "openrouter-api": "openai/gpt-oss-120b:free",
}


def normalize_model_value(model: str | None) -> str:
    value = (model or "").strip()
    if value == DEFAULT_MODEL_VALUE:
        return ""
    return value


def is_valid_runtime(runtime_kind: str | None) -> bool:
    return (runtime_kind or "").strip() in RUNTIME_MODEL_OPTIONS


def is_valid_runtime_model_pair(runtime_kind: str | None, model: str | None) -> bool:
    runtime = (runtime_kind or "").strip()
    normalized_model = normalize_model_value(model)
    allowed = RUNTIME_MODEL_OPTIONS.get(runtime)
    if allowed is None:
        return False
    return normalized_model in allowed


def default_model_for_runtime(runtime_kind: str | None) -> str:
    runtime = (runtime_kind or "").strip()
    return DEFAULT_MODEL_BY_RUNTIME.get(runtime, "")


def normalize_runtime_model_pair(runtime_kind: str | None, model: str | None) -> tuple[str, str]:
    runtime = (runtime_kind or "").strip()
    if not is_valid_runtime(runtime):
        raise ValidationError(
            message=f"Unknown runtime '{runtime}'",
            details={"runtime_kind": runtime},
        )
    normalized_model = normalize_model_value(model)
    if not normalized_model:
        return runtime, default_model_for_runtime(runtime)
    if not is_valid_runtime_model_pair(runtime, normalized_model):
        raise ValidationError(
            message=f"Model '{normalized_model}' is not valid for runtime '{runtime}'",
            details={"runtime_kind": runtime, "model": normalized_model},
        )
    return runtime, normalized_model
