"""Determine the workflow category for status-classification purposes.

The classifier is intentionally tolerant: it first looks for an explicit
``category`` key inside the workflow's ``definition_json`` (seeded value),
then falls back to name-pattern matching, and finally returns ``unknown``.

This avoids a database migration while still giving deterministic,
project-wide classification for all crypto workflows.
"""

from __future__ import annotations

import re
from typing import Any

_WORKFLOW_CATEGORIES = frozenset({"trade", "monitor", "research", "screener", "unknown"})

# Ordered: first match wins. Patterns should be conservative enough that
# "Trade Pipeline" beats "Market Watch" etc.
_NAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Trade\s+Pipeline", re.IGNORECASE), "trade"),
    (re.compile(r"Position\s+Monitor", re.IGNORECASE), "monitor"),
    (re.compile(r"Market\s+Watch|Research", re.IGNORECASE), "research"),
    (re.compile(r"Screener", re.IGNORECASE), "screener"),
]


def classify_workflow_category(
    workflow: Any | None = None,
    workflow_name: str | None = None,
) -> str:
    """Return one of ``trade|monitor|research|screener|unknown``.

    Args:
        workflow: A ``Workflow`` ORM instance or any object with a
            ``definition_json`` attribute and/or ``name`` attribute.
        workflow_name: Optional explicit name override. Used when only the
            name string is available (e.g., from an API response).
    """
    definition_category = ""
    name = workflow_name or ""

    if workflow is not None:
        name = name or getattr(workflow, "name", "") or ""
        definition = getattr(workflow, "definition_json", None) or {}
        if isinstance(definition, dict):
            definition_category = definition.get("category", "")

    if definition_category in _WORKFLOW_CATEGORIES:
        return definition_category

    for pattern, category in _NAME_PATTERNS:
        if pattern.search(name):
            return category

    return "unknown"
