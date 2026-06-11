"""Utilities for extracting JSON objects from LLM text output."""

from __future__ import annotations

import json


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

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    return _loads_object(candidate[start : end + 1])


def _loads_object(value: str) -> dict | None:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload
