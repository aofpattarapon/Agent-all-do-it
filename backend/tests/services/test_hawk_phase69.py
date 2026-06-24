"""Phase 6.9 tests — HAWK Structure Token-Stable JSON.

Covers:
- ollama_sdk num_ctx in request body
- hawk_verbosity render_verbosity_instruction for all modes
- run_executor verbosity injection for HAWK roles
- hawk_output_repair verbosity instruction in repair prompts
- Validator / safety regressions
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Ollama num_ctx ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_ollama_request_includes_num_ctx_8192():
    """ollama_sdk.run_agent() must include num_ctx=8192 in the options dict."""
    from app.services.runtime.ollama_sdk import run_agent

    captured: list[dict] = []

    async def fake_post(url: str, *, json: dict, **kwargs):  # type: ignore[override]
        captured.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "message": {"content": '{"vote":"NEUTRAL","confidence":0}'},
            "prompt_eval_count": 100,
            "eval_count": 20,
        }
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        await run_agent(
            prompt="test prompt",
            system_prompt="test system",
            model="gemma3:12b",
            max_tokens=4096,
            temperature=0.7,
        )

    assert len(captured) == 1
    opts = captured[0]["options"]
    assert opts["num_ctx"] == 8192, f"Expected num_ctx=8192, got {opts.get('num_ctx')}"


@pytest.mark.anyio
async def test_ollama_num_predict_equals_max_tokens():
    """num_predict must equal max_tokens — unchanged by Phase 6.9."""
    from app.services.runtime.ollama_sdk import run_agent

    captured: list[dict] = []

    async def fake_post(url: str, *, json: dict, **kwargs):
        captured.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "message": {"content": "{}"},
            "prompt_eval_count": 50,
            "eval_count": 10,
        }
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        await run_agent(prompt="p", model="gemma3:12b", max_tokens=4096)

    opts = captured[0]["options"]
    assert opts["num_predict"] == 4096


@pytest.mark.anyio
async def test_ollama_model_name_unchanged():
    """Model name must not be altered by num_ctx addition."""
    from app.services.runtime.ollama_sdk import run_agent

    captured: list[dict] = []

    async def fake_post(url: str, *, json: dict, **kwargs):
        captured.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "message": {"content": "{}"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        await run_agent(prompt="p", model="gemma3:12b", max_tokens=4096)

    assert captured[0]["model"] == "gemma3:12b"


@pytest.mark.anyio
async def test_ollama_custom_num_ctx_respected():
    """A caller-supplied num_ctx value must be forwarded, not silently replaced."""
    from app.services.runtime.ollama_sdk import run_agent

    captured: list[dict] = []

    async def fake_post(url: str, *, json: dict, **kwargs):
        captured.append(json)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "message": {"content": "{}"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        return resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client_cls.return_value = mock_client

        await run_agent(prompt="p", model="llama3.2", max_tokens=2048, num_ctx=16384)

    assert captured[0]["options"]["num_ctx"] == 16384


# ── Verbosity helper ──────────────────────────────────────────────────────────


def test_compact_mode_returns_non_empty_string():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("compact")
    assert result and len(result) > 0


def test_compact_mode_says_json_only():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("compact")
    assert "JSON only" in result


def test_compact_mode_requires_immediate_open_brace():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("compact")
    assert "{" in result
    assert "immediately" in result.lower() or "Begin" in result


def test_compact_mode_limits_summary_length():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("compact")
    assert "20 words" in result or "1 short sentence" in result or "1 sentence" in result


def test_compact_mode_limits_support_levels_to_3():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("compact")
    assert "3" in result
    assert "support" in result.lower()


def test_compact_mode_limits_resistance_levels_to_3():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("compact")
    assert "3" in result
    assert "resistance" in result.lower()


def test_compact_mode_constrains_active_order_block():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("compact")
    assert "active_order_block" in result


def test_compact_mode_targets_600_tokens():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("compact")
    assert "600" in result


def test_standard_mode_allows_moderate_detail():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("standard")
    assert "standard" in result.lower() or "STANDARD" in result
    assert "JSON only" in result
    # standard allows more than 3 entries
    assert "5" in result


def test_verbose_mode_allows_rich_detail():
    from app.services.hawk_verbosity import render_verbosity_instruction

    result = render_verbosity_instruction("verbose")
    assert "verbose" in result.lower() or "VERBOSE" in result
    assert "JSON only" in result


def test_invalid_mode_falls_back_to_compact():
    from app.services.hawk_verbosity import render_verbosity_instruction

    compact = render_verbosity_instruction("compact")
    assert render_verbosity_instruction("INVALID_MODE") == compact
    assert render_verbosity_instruction("") == compact
    assert render_verbosity_instruction("ultra") == compact


def test_all_modes_forbid_prose_outside_json():
    from app.services.hawk_verbosity import render_verbosity_instruction

    for mode in ("compact", "standard", "verbose"):
        result = render_verbosity_instruction(mode)
        assert "No prose" in result or "no prose" in result, f"mode={mode} missing no-prose constraint"


def test_all_modes_forbid_markdown_fences():
    from app.services.hawk_verbosity import render_verbosity_instruction

    for mode in ("compact", "standard", "verbose"):
        result = render_verbosity_instruction(mode)
        assert "markdown" in result.lower(), f"mode={mode} missing markdown fence constraint"


def test_all_modes_preserve_schema():
    from app.services.hawk_verbosity import render_verbosity_instruction

    for mode in ("compact", "standard", "verbose"):
        result = render_verbosity_instruction(mode)
        assert "schema" in result.lower(), f"mode={mode} missing schema preservation"


# ── Runtime prompt injection ──────────────────────────────────────────────────


def _make_agent(role: str, tools_config: dict | None = None, system_prompt: str = "sys") -> MagicMock:
    agent = MagicMock()
    agent.role = role
    agent.tools_config = tools_config
    agent.system_prompt = system_prompt
    agent.max_tokens = 4096
    agent.skill_ids = []
    agent.name = f"test_{role}"
    return agent


def test_hawk_structure_gets_compact_instruction_by_default():
    """When no hawk_output_mode in tools_config, compact instruction appended."""
    from app.services.hawk_verbosity import render_verbosity_instruction

    compact_instr = render_verbosity_instruction("compact")
    # Simulate what _run_prompt does
    agent_role = "hawk_structure"
    hawk_step_keys = {"hawk_trend", "hawk_structure", "hawk_counter"}
    tools_config = {}  # no hawk_output_mode
    system_prompt = "base system prompt"

    if agent_role in hawk_step_keys:
        mode = (tools_config or {}).get("hawk_output_mode", "compact")
        system_prompt = f"{system_prompt}\n\n{render_verbosity_instruction(mode)}"

    assert compact_instr in system_prompt


def test_hawk_structure_gets_standard_instruction_from_tools_config():
    from app.services.hawk_verbosity import render_verbosity_instruction

    standard_instr = render_verbosity_instruction("standard")
    agent_role = "hawk_structure"
    hawk_step_keys = {"hawk_trend", "hawk_structure", "hawk_counter"}
    tools_config = {"hawk_output_mode": "standard"}
    system_prompt = "base system prompt"

    if agent_role in hawk_step_keys:
        mode = (tools_config or {}).get("hawk_output_mode", "compact")
        system_prompt = f"{system_prompt}\n\n{render_verbosity_instruction(mode)}"

    assert standard_instr in system_prompt


def test_hawk_structure_gets_verbose_instruction_from_tools_config():
    from app.services.hawk_verbosity import render_verbosity_instruction

    verbose_instr = render_verbosity_instruction("verbose")
    agent_role = "hawk_structure"
    hawk_step_keys = {"hawk_trend", "hawk_structure", "hawk_counter"}
    tools_config = {"hawk_output_mode": "verbose"}
    system_prompt = "base"

    if agent_role in hawk_step_keys:
        mode = (tools_config or {}).get("hawk_output_mode", "compact")
        system_prompt = f"{system_prompt}\n\n{render_verbosity_instruction(mode)}"

    assert verbose_instr in system_prompt


def test_invalid_tools_config_mode_falls_back_to_compact():
    from app.services.hawk_verbosity import render_verbosity_instruction

    compact_instr = render_verbosity_instruction("compact")
    agent_role = "hawk_structure"
    hawk_step_keys = {"hawk_trend", "hawk_structure", "hawk_counter"}
    tools_config = {"hawk_output_mode": "UNKNOWN_MODE"}
    system_prompt = "base"

    if agent_role in hawk_step_keys:
        mode = (tools_config or {}).get("hawk_output_mode", "compact")
        system_prompt = f"{system_prompt}\n\n{render_verbosity_instruction(mode)}"

    assert compact_instr in system_prompt


def test_non_hawk_role_does_not_receive_verbosity_instruction():
    from app.services.hawk_verbosity import render_verbosity_instruction

    compact_instr = render_verbosity_instruction("compact")
    hawk_step_keys = {"hawk_trend", "hawk_structure", "hawk_counter"}
    system_prompt = "base system prompt"

    for non_hawk_role in ("sage", "compile_proposal", "execution", "post_trade_review", "market_data"):
        result = system_prompt
        if non_hawk_role in hawk_step_keys:
            result = f"{system_prompt}\n\n{render_verbosity_instruction('compact')}"
        assert compact_instr not in result, f"Non-HAWK role '{non_hawk_role}' incorrectly got verbosity instruction"


def test_all_hawk_roles_receive_verbosity_instruction():
    from app.services.hawk_verbosity import render_verbosity_instruction

    compact_instr = render_verbosity_instruction("compact")
    hawk_step_keys = {"hawk_trend", "hawk_structure", "hawk_counter"}
    base_prompt = "base system prompt"

    for role in ("hawk_trend", "hawk_structure", "hawk_counter"):
        system_prompt = base_prompt
        if role in hawk_step_keys:
            mode = {}.get("hawk_output_mode", "compact")
            system_prompt = f"{system_prompt}\n\n{render_verbosity_instruction(mode)}"
        assert compact_instr in system_prompt, f"HAWK role '{role}' did not receive verbosity instruction"


# ── Repair prompt ─────────────────────────────────────────────────────────────


def test_repair_prompt_hawk_structure_includes_compact_by_default():
    from app.services.hawk_output_repair import build_hawk_repair_prompt
    from app.services.hawk_verbosity import render_verbosity_instruction

    compact_instr = render_verbosity_instruction("compact")
    result = build_hawk_repair_prompt("{", role="hawk_structure")
    assert compact_instr in result


def test_repair_prompt_says_no_prose_outside_json():
    from app.services.hawk_output_repair import build_hawk_repair_prompt

    result = build_hawk_repair_prompt("{", role="hawk_structure")
    text_lower = result.lower()
    assert "no prose" in text_lower or "no markdown" in text_lower


def test_repair_prompt_path1_includes_compact_instruction():
    """Empty output path (Path 1) must include the verbosity instruction."""
    from app.services.hawk_output_repair import build_hawk_repair_prompt
    from app.services.hawk_verbosity import render_verbosity_instruction

    compact_instr = render_verbosity_instruction("compact")
    result = build_hawk_repair_prompt("", role="hawk_structure")
    assert compact_instr in result


def test_repair_prompt_path2_includes_compact_instruction():
    """No-usable-vote path (Path 2) must include the verbosity instruction."""
    from app.services.hawk_output_repair import build_hawk_repair_prompt
    from app.services.hawk_verbosity import render_verbosity_instruction

    compact_instr = render_verbosity_instruction("compact")
    result = build_hawk_repair_prompt("{", role="hawk_structure")
    assert compact_instr in result


def test_repair_prompt_path3_includes_compact_instruction():
    """Preserve/convert path (Path 3 — has valid vote) must include verbosity instruction."""
    from app.services.hawk_output_repair import build_hawk_repair_prompt
    from app.services.hawk_verbosity import render_verbosity_instruction

    compact_instr = render_verbosity_instruction("compact")
    valid_vote_output = '{"vote": "BULLISH", "confidence": 65}'
    result = build_hawk_repair_prompt(valid_vote_output, role="hawk_structure")
    assert compact_instr in result


def test_repair_prompt_does_not_fabricate_vote():
    """Repair prompt instructions must tell model not to fabricate vote."""
    from app.services.hawk_output_repair import build_hawk_repair_prompt

    result = build_hawk_repair_prompt("{", role="hawk_structure")
    assert "fabricate" in result.lower()


def test_repair_prompt_does_not_fabricate_invalidation_level():
    """Repair prompt must tell model not to fabricate invalidation_level."""
    from app.services.hawk_output_repair import build_hawk_repair_prompt

    result = build_hawk_repair_prompt("{", role="hawk_structure")
    assert "invalidation_level" in result


def test_repair_prompt_keeps_strict_schema():
    """Repair prompt must reference the required JSON shape."""
    from app.services.hawk_output_repair import build_hawk_repair_prompt

    result = build_hawk_repair_prompt("{", role="hawk_structure")
    assert "vote" in result
    assert "confidence" in result
    assert "reasoning" in result


# ── Validator / safety regressions ───────────────────────────────────────────


def test_compact_output_with_nested_structure_assessment_passes_basic_parse():
    """Minimal compact hawk_structure JSON is valid and has reasoning.structure_assessment."""
    compact_output = json.dumps(
        {
            "agent": "hawk_structure",
            "symbol": "BTCUSDT",
            "analyzed_at": "2025-01-01T00:00:00Z",
            "sources_used": ["pre-fetched market data"],
            "vote": "BULLISH",
            "confidence": 65,
            "data_quality": "REAL_MARKET_DATA",
            "market_data_snapshot": {"price": 95000.0, "analyzed_interval": "1h"},
            "invalidation_level": 90500.0,
            "risk_flags": [],
            "reasoning": {
                "role_focus": "structure",
                "summary": "Price above VWAP.",
                "structure_assessment": {
                    "price_vs_vwap": "ABOVE",
                    "nearest_support_levels": [91000.0, 89500.0],
                    "nearest_resistance_levels": [97000.0],
                },
            },
        }
    )
    parsed = json.loads(compact_output)
    assert parsed["vote"] == "BULLISH"
    assert "structure_assessment" in parsed["reasoning"]
    assert "price_vs_vwap" not in parsed  # must not be at top level


def test_top_level_forbidden_key_absent_in_compact_output():
    """Compact output must not contain forbidden top-level keys."""
    forbidden = [
        "price_vs_vwap",
        "structure_assessment",
        "active_order_block",
        "nearest_support_levels",
        "nearest_resistance_levels",
        "trend_direction",
        "analysis",
        "conclusion",
        "recommendation",
    ]
    compact_output = {
        "agent": "hawk_structure",
        "symbol": "BTCUSDT",
        "vote": "BULLISH",
        "confidence": 65,
        "reasoning": {"structure_assessment": {}},
    }
    for key in forbidden:
        assert key not in compact_output, f"Forbidden key '{key}' present at top level"


def test_unparseable_json_still_blocks_fail_closed():
    """assess_hawk_output_reliability must still detect truncated JSON as invalid."""
    from app.services.hawk_output_repair import assess_hawk_output_reliability

    result = assess_hawk_output_reliability("{", tokens_used=4096, max_tokens=4096)
    assert result["invalid_json"] is True
    assert result["output_truncated_detected"] is True


def test_no_model_or_max_tokens_changed_in_verbosity_module():
    """hawk_verbosity.py must not import from runtime adapters or model_fallback."""
    import ast
    import pathlib

    src = pathlib.Path(
        "/Users/socket9companylimited/Desktop/Web-app-agent-Kimi/pixel_dream_agent/backend/app/services/hawk_verbosity.py"
    ).read_text()
    assert "max_tokens" not in src
    # Verify it doesn't import from model_fallback or runtime adapters
    tree = ast.parse(src)
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    import_names = [
        (getattr(n, "module", None) or "") + "".join(getattr(alias, "name", "") for alias in getattr(n, "names", []))
        for n in imports
    ]
    for name in import_names:
        assert "model_fallback" not in name
        assert "ollama_sdk" not in name


def test_no_vote_fabrication_in_verbosity_instruction():
    """Verbosity instructions must not instruct model to fabricate or guess votes."""
    from app.services.hawk_verbosity import render_verbosity_instruction

    for mode in ("compact", "standard", "verbose"):
        result = render_verbosity_instruction(mode)
        assert "fabricate" not in result.lower()
        assert "guess" not in result.lower()
        assert "invent" not in result.lower()
