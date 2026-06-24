"""HAWK output verbosity mode instructions.

Controls how much prose/detail HAWK agents generate per call.
Lower verbosity = fewer output tokens = fits within local/Ollama context budgets.

Modes
-----
compact  — default for local Ollama (gemma3:12b). Under 600 output tokens.
standard — for mid-range or API-backed models. Moderate detail.
verbose  — for large cloud models with wide output budgets.

All modes share the same strict HAWK JSON schema. Verbosity only controls
list length, summary depth, and active_order_block field count.
"""

from __future__ import annotations

_COMPACT_INSTRUCTION = """\
OUTPUT VERBOSITY: COMPACT MODE
- Begin your response immediately with the character {. No preamble. No text before the JSON.
- Return JSON only. No markdown fences. No code blocks. No prose after the closing }.
- summary: max 1 short sentence (20 words or fewer).
- nearest_support_levels: include at most 3 values.
- nearest_resistance_levels: include at most 3 values.
- active_order_block: include only type and strength fields.
- risk_flags: list at most 2 entries; use [] if none apply.
- reasoning.structure_assessment: include price_vs_vwap, nearest_support_levels, nearest_resistance_levels, active_order_block, conclusion only.
- Target total output: under 600 tokens.
- Keep the same strict JSON schema — do not add keys, do not remove required keys, do not emit role-specific fields at the top level."""

_STANDARD_INSTRUCTION = """\
OUTPUT VERBOSITY: STANDARD MODE
- Begin your response immediately with the character {. No preamble. No text before the JSON.
- Return JSON only. No markdown fences. No code blocks. No prose after the closing }.
- summary: max 2 to 4 sentences.
- nearest_support_levels: include at most 5 values.
- nearest_resistance_levels: include at most 5 values.
- active_order_block: include type, strength, and zone fields.
- Keep the same strict JSON schema — do not add keys, do not remove required keys, do not emit role-specific fields at the top level."""

_VERBOSE_INSTRUCTION = """\
OUTPUT VERBOSITY: VERBOSE MODE
- Begin your response immediately with the character {. No preamble. No text before the JSON.
- Return JSON only. No markdown fences. No code blocks. No prose after the closing }.
- summary: detailed multi-sentence analysis permitted.
- nearest_support_levels: up to 10 values.
- nearest_resistance_levels: up to 10 values.
- active_order_block: full fields including zone_low, zone_high, and extended description.
- Keep the same strict JSON schema — do not add keys, do not remove required keys, do not emit role-specific fields at the top level."""

_MODE_MAP: dict[str, str] = {
    "compact": _COMPACT_INSTRUCTION,
    "standard": _STANDARD_INSTRUCTION,
    "verbose": _VERBOSE_INSTRUCTION,
}


def render_verbosity_instruction(mode: str) -> str:
    """Return a mode-specific output constraint block for HAWK system prompts.

    Invalid or missing modes fall back to compact (safest for local/Ollama).
    """
    return _MODE_MAP.get(mode, _COMPACT_INSTRUCTION)
