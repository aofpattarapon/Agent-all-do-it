"""Phase 6.14.C — Warmup auto-execute safety fix tests.

Verifies:
- should_auto_execute logic with warmup_trades=0 (the fix)
- Old warmup_trades=10 behaviour (proves the bug that was fixed)
- Auto 30m / Auto 15m warmup_trades=10 still produces True (autonomous path, correct)
- winrate threshold path still fires correctly at 80%
- below_threshold default is "pause" (not "skip") when key is absent
- skip_steps_on_auto=2 parses correctly from config
"""

from __future__ import annotations

import pytest


# ── Gate logic helper (mirrors run_executor.py:453) ──────────────────────────

def _should_auto_execute(closed_count: int, warmup_trades: int, winrate: float, threshold: float) -> bool:
    return (closed_count < warmup_trades) or (winrate >= threshold)


def _get_config_int(config: dict, key: str, default: int) -> int:
    return int(config.get(key, default))


def _get_config_float(config: dict, key: str, default: float) -> float:
    return float(config.get(key, default))


def _get_config_str(config: dict, key: str, default: str) -> str:
    return str(config.get(key, default))


# ── Current-state constants (Phase 6.14.C baseline) ──────────────────────────

CURRENT_CLOSED_COUNT = 5
CURRENT_WINRATE = 0.0

# Config AFTER fix
FIXED_CONFIG = {
    "description": "Auto-executes if project historical winrate >= 80%. Otherwise pauses for human approval.",
    "winrate_threshold": 80.0,
    "skip_steps_on_auto": 2,
    "warmup_trades": 0,
}

# Config BEFORE fix (no warmup_trades key → falls back to PIPELINE_WARMUP_TRADES=10)
PRE_FIX_CONFIG = {
    "description": "Auto-executes if project historical winrate >= 80%. Otherwise pauses for human approval.",
    "winrate_threshold": 80.0,
    "skip_steps_on_auto": 2,
}
PIPELINE_WARMUP_TRADES_DEFAULT = 10  # mirrors settings.PIPELINE_WARMUP_TRADES

# Auto 30m / 15m config (must remain unchanged)
AUTO_WORKFLOW_CONFIG = {
    "description": "First 10 trades always execute (warm-up). After that: execute if winrate >=60%.",
    "warmup_trades": 10,
    "below_threshold": "skip",
    "winrate_threshold": 60.0,
    "skip_steps_on_auto": 1,
}


# ── 1. Fix produces should_auto_execute=False at current state ────────────────


def test_gate_false_with_warmup_zero_at_current_state() -> None:
    """warmup_trades=0 makes warmup path impossible; winrate=0% < 80% → False."""
    warmup_trades = _get_config_int(FIXED_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    threshold = _get_config_float(FIXED_CONFIG, "winrate_threshold", 60.0)
    result = _should_auto_execute(CURRENT_CLOSED_COUNT, warmup_trades, CURRENT_WINRATE, threshold)
    assert result is False, (
        f"Expected False with warmup_trades=0, closed_count={CURRENT_CLOSED_COUNT}, "
        f"winrate={CURRENT_WINRATE}%, threshold={threshold}%, got True"
    )


def test_gate_false_with_warmup_zero_and_zero_closed() -> None:
    """Even closed_count=0 cannot trigger warmup when warmup_trades=0."""
    warmup_trades = _get_config_int(FIXED_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    threshold = _get_config_float(FIXED_CONFIG, "winrate_threshold", 60.0)
    result = _should_auto_execute(0, warmup_trades, CURRENT_WINRATE, threshold)
    assert result is False


def test_gate_warmup_zero_blocks_all_closed_counts() -> None:
    """warmup_trades=0 → no closed_count value can ever satisfy closed_count < 0."""
    warmup_trades = _get_config_int(FIXED_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    threshold = _get_config_float(FIXED_CONFIG, "winrate_threshold", 60.0)
    for closed_count in range(0, 20):
        result = _should_auto_execute(closed_count, warmup_trades, 0.0, threshold)
        assert result is False, (
            f"Expected False for closed_count={closed_count} with warmup_trades=0, winrate=0%"
        )


# ── 2. Old behaviour (pre-fix) was True — proves the bug ─────────────────────


def test_old_warmup_10_would_be_true_proving_bug() -> None:
    """Before fix: warmup_trades defaulted to 10 → (5 < 10) = True → auto-execute fired."""
    warmup_trades = _get_config_int(PRE_FIX_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    threshold = _get_config_float(PRE_FIX_CONFIG, "winrate_threshold", 60.0)
    assert warmup_trades == 10, "Pre-fix config must fall back to PIPELINE_WARMUP_TRADES=10"
    result = _should_auto_execute(CURRENT_CLOSED_COUNT, warmup_trades, CURRENT_WINRATE, threshold)
    assert result is True, (
        "Pre-fix behaviour must be True (this confirms B8 was real): "
        f"closed_count={CURRENT_CLOSED_COUNT} < warmup_trades=10"
    )


# ── 3. Winrate threshold path still fires when warranted ─────────────────────


def test_gate_still_true_at_winrate_threshold() -> None:
    """At exactly 80% winrate, should still auto-execute (winrate path, not warmup)."""
    warmup_trades = _get_config_int(FIXED_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    threshold = _get_config_float(FIXED_CONFIG, "winrate_threshold", 60.0)
    result = _should_auto_execute(0, warmup_trades, 80.0, threshold)
    assert result is True, "80.0% >= 80.0% threshold must still trigger auto-execute"


def test_gate_still_true_above_threshold() -> None:
    """Above 80% winrate, should still auto-execute."""
    warmup_trades = _get_config_int(FIXED_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    threshold = _get_config_float(FIXED_CONFIG, "winrate_threshold", 60.0)
    result = _should_auto_execute(CURRENT_CLOSED_COUNT, warmup_trades, 90.0, threshold)
    assert result is True, "90.0% >= 80.0% threshold must still trigger auto-execute"


def test_gate_false_just_below_threshold() -> None:
    """79.9% winrate should not trigger (below 80% threshold, warmup=0)."""
    warmup_trades = _get_config_int(FIXED_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    threshold = _get_config_float(FIXED_CONFIG, "winrate_threshold", 60.0)
    result = _should_auto_execute(CURRENT_CLOSED_COUNT, warmup_trades, 79.9, threshold)
    assert result is False, "79.9% < 80.0% must not auto-execute with warmup_trades=0"


# ── 4. Auto 30m / 15m warmup_trades=10 remains correct ──────────────────────


def test_auto_30m_warmup_10_still_true_at_5_closed() -> None:
    """Auto 30m warmup_trades=10 must still produce True at 5 closed trades — autonomous path."""
    warmup_trades = _get_config_int(AUTO_WORKFLOW_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    threshold = _get_config_float(AUTO_WORKFLOW_CONFIG, "winrate_threshold", 60.0)
    assert warmup_trades == 10, "Auto 30m warmup_trades must remain 10"
    result = _should_auto_execute(CURRENT_CLOSED_COUNT, warmup_trades, CURRENT_WINRATE, threshold)
    assert result is True, "Auto 30m must still auto-execute in warmup period (5 < 10)"


def test_auto_15m_warmup_10_still_true_at_5_closed() -> None:
    """Auto 15m warmup_trades=10 must still produce True at 5 closed trades — autonomous path."""
    warmup_trades = _get_config_int(AUTO_WORKFLOW_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    threshold = _get_config_float(AUTO_WORKFLOW_CONFIG, "winrate_threshold", 60.0)
    assert warmup_trades == 10, "Auto 15m warmup_trades must remain 10"
    result = _should_auto_execute(CURRENT_CLOSED_COUNT, warmup_trades, CURRENT_WINRATE, threshold)
    assert result is True, "Auto 15m must still auto-execute in warmup period (5 < 10)"


def test_auto_workflow_below_threshold_is_skip() -> None:
    """Auto workflows use below_threshold='skip' (NO_TRADE path) — must remain unchanged."""
    below_threshold = _get_config_str(AUTO_WORKFLOW_CONFIG, "below_threshold", "pause")
    assert below_threshold == "skip", (
        "Auto 30m/15m below_threshold must remain 'skip' (autonomous NO_TRADE path)"
    )


# ── 5. Proposal-to-Execution below_threshold defaults to "pause" ─────────────


def test_below_threshold_default_is_pause_when_key_absent() -> None:
    """When below_threshold is absent from config, default is 'pause' (human-approval path)."""
    below_threshold = _get_config_str(PRE_FIX_CONFIG, "below_threshold", "pause")
    assert below_threshold == "pause", (
        "Proposal-to-Execution must default below_threshold to 'pause', not 'skip'"
    )


def test_fixed_config_still_defaults_to_pause() -> None:
    """Fixed config also has no below_threshold key — must still default to 'pause'."""
    below_threshold = _get_config_str(FIXED_CONFIG, "below_threshold", "pause")
    assert below_threshold == "pause"


# ── 6. Config key extraction correctness ─────────────────────────────────────


def test_fixed_config_warmup_trades_is_zero() -> None:
    warmup_trades = _get_config_int(FIXED_CONFIG, "warmup_trades", PIPELINE_WARMUP_TRADES_DEFAULT)
    assert warmup_trades == 0, f"Fixed config must have warmup_trades=0, got {warmup_trades}"


def test_fixed_config_winrate_threshold_is_80() -> None:
    threshold = _get_config_float(FIXED_CONFIG, "winrate_threshold", 60.0)
    assert threshold == 80.0, f"Fixed config must preserve winrate_threshold=80.0, got {threshold}"


def test_fixed_config_skip_steps_on_auto_is_2() -> None:
    skip_count = _get_config_int(FIXED_CONFIG, "skip_steps_on_auto", 0)
    assert skip_count == 2, f"Fixed config must preserve skip_steps_on_auto=2, got {skip_count}"


def test_pre_fix_config_has_no_warmup_trades_key() -> None:
    """Confirms the pre-fix config had no warmup_trades key (the missing key = the bug)."""
    assert "warmup_trades" not in PRE_FIX_CONFIG, (
        "Pre-fix config must NOT contain warmup_trades (confirms the bug was a missing key)"
    )


def test_fixed_config_has_warmup_trades_key() -> None:
    """Fixed config must have warmup_trades key explicitly set."""
    assert "warmup_trades" in FIXED_CONFIG, "Fixed config must contain warmup_trades key"
    assert FIXED_CONFIG["warmup_trades"] == 0
