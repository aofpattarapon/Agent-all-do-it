"""Utilities for extracting JSON objects from LLM text output."""

from __future__ import annotations

import json
from typing import Any


def _extract_balanced_object(text: str) -> tuple[str | None, bool]:
    """Extract the first balanced JSON object using brace counting.

    Returns (extracted_str, was_truncated):
      (str, False)  — found a complete balanced {...} object
      (None, True)  — opening brace found but braces never closed (truncated input)
      (None, False) — no opening brace present
    """
    start = text.find("{")
    if start == -1:
        return None, False

    depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1], False

    # Opening brace was found but never closed.
    return None, True


def extract_json_object(text: str) -> dict | None:
    """Best-effort parse of a JSON object from raw model output.

    Supports plain JSON, fenced ```json blocks, and prose-wrapped JSON where
    the first top-level object is the meaningful payload.
    """
    candidate = (text or "").strip()
    if not candidate:
        return None

    direct = _loads_object(candidate)
    if direct is not None:
        return direct

    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines:
            lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()
        fenced = "\n".join(lines).strip()
        direct = _loads_object(fenced)
        if direct is not None:
            return direct
        candidate = fenced or candidate

    # Balanced-brace extraction: handles prose before/after and ignores truncated input.
    extracted, _truncated = _extract_balanced_object(candidate)
    if extracted is not None:
        return _loads_object(extracted)
    return None


def normalize_llm_json_output(text: str) -> tuple[dict | None, dict[str, Any]]:
    """Parse LLM output that may be markdown-fenced, prose-wrapped, or truncated.

    Returns ``(parsed_dict | None, metadata)``.

    Metadata keys:
      had_markdown_fence    — True when the output began with triple backticks
      repaired_json_wrapper — True when JSON was successfully extracted after fence/prose removal
      truncated_detected    — True when an opening brace was found but never balanced
      parse_error           — descriptive failure string, or None on success
    """
    meta: dict[str, Any] = {
        "had_markdown_fence": False,
        "repaired_json_wrapper": False,
        "truncated_detected": False,
        "parse_error": None,
    }

    candidate = (text or "").strip()
    if not candidate:
        meta["parse_error"] = "empty_output"
        return None, meta

    # 1. Direct parse — fastest path; no repair metadata needed.
    direct = _loads_object(candidate)
    if direct is not None:
        return direct, meta

    # 2. Markdown fence stripping.
    if candidate.startswith("```"):
        meta["had_markdown_fence"] = True
        lines = candidate.splitlines()
        if lines:
            lines = lines[1:]  # drop opening fence line (```json or ```)
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()  # drop closing fence line
        candidate = "\n".join(lines).strip()

        direct = _loads_object(candidate)
        if direct is not None:
            meta["repaired_json_wrapper"] = True
            return direct, meta

    # 3. Balanced-brace extraction — handles prose around JSON and detects truncation.
    extracted, truncated = _extract_balanced_object(candidate)
    if truncated:
        meta["truncated_detected"] = True
        meta["parse_error"] = "compile_proposal_invalid_json_truncated"
        return None, meta

    if extracted is not None:
        parsed = _loads_object(extracted)
        if parsed is not None:
            meta["repaired_json_wrapper"] = True
            return parsed, meta
        meta["parse_error"] = "balanced_braces_found_but_json_invalid"
        return None, meta

    # 4. No JSON object found at all.
    meta["parse_error"] = "no_json_object_found"
    return None, meta


def _loads_object(value: str) -> dict | None:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload
