"""Phase W31E — tests for the DEMO Guarded Auto-Approval decision engine.

The policy is pure (no DB / no exchange I/O), so these are plain sync tests. They prove
that every guard blocks as designed and that AUTO_APPROVED_DEMO is reachable ONLY when
every guard passes — and that no live-order path exists in the policy module.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.demo_auto_approval import (
    AutoApprovalInputs,
    AutoApprovalSettings,
    evaluate_auto_approval,
)

NOW = datetime(2026, 6, 23, 2, 30, 0, tzinfo=UTC)


def _cfg(**overrides) -> AutoApprovalSettings:
    base = {
        "enabled": True,
        "scope": "demo_ready_watch_only",
        "max_notional_usdt": 50.0,
        "max_open_positions": 1,
        "max_orders_per_day": 1,
        "ready_confirmation_ticks": 2,
        "ready_max_age_seconds": 300,
        "cooldown_minutes": 60,
        "require_exchange_flat": True,
        "require_hawk_2_of_3": True,
        "require_sage_approval": True,
        "require_sl_tp_rr_preflight": True,
        "require_demo_mode": True,
        "block_if_consecutive_loss_ack_missing": True,
    }
    base.update(overrides)
    return AutoApprovalSettings(**base)


def _ready_posture(
    *,
    age_seconds: int = 10,
    hawk_stale: bool = False,
    gate_passed: bool = True,
    majority: str = "BULLISH",
    overall: str = "READY",
    ready_symbols: int = 1,
) -> dict:
    gen = (NOW - timedelta(seconds=age_seconds)).isoformat()
    candidates = []
    for i, sym in enumerate(("SOLUSDT", "ETHUSDT", "BTCUSDT")):
        posture = "READY" if i < ready_symbols else "WATCH_ONLY"
        candidates.append(
            {
                "symbol": sym,
                "posture": posture,
                "latest_hawk_read": {
                    "majority_direction": majority,
                    "gate_passed": gate_passed,
                    "is_stale": hawk_stale,
                },
            }
        )
    return {"generated_at": gen, "overall_posture": overall, "candidates": candidates}


def _inputs(**overrides) -> AutoApprovalInputs:
    base = {
        "posture": _ready_posture(),
        "now": NOW,
        "trading_mode": "DEMO",
        "exchange_mode": "demo",
        "market_type": "futures",
        "live_trading_enabled": False,
        "exchange_flat": True,
        "open_positions": 0,
        "auto_orders_today": 0,
        "last_auto_order_at": None,
        "ready_confirmations": 2,
        "consecutive_loss_block_armed": False,
        "consecutive_loss_ack_present": False,
        "runtime_guardrails_intact": True,
        "sage_precheck": None,
        "preflight_precheck": None,
    }
    base.update(overrides)
    return AutoApprovalInputs(**base)


def test_all_guards_pass_yields_auto_approved_demo():
    d = evaluate_auto_approval(_cfg(), _inputs())
    assert d.approved
    assert d.outcome == "AUTO_APPROVED_DEMO"
    assert d.symbol == "SOLUSDT"
    assert d.direction == "LONG"
    assert d.notional_usdt == 50.0
    assert "sage_review" in d.downstream_gates_still_enforced
    assert "execution_preflight_min_notional_lot_size" in d.downstream_gates_still_enforced


def test_disabled_blocks():
    d = evaluate_auto_approval(_cfg(enabled=False), _inputs())
    assert not d.approved and d.reason == "auto_approval_disabled"


def test_hold_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(posture=_ready_posture(overall="HOLD")))
    assert not d.approved and d.reason == "not_ready"


def test_stale_ready_snapshot_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(posture=_ready_posture(age_seconds=3600)))
    assert not d.approved and d.reason == "ready_stale"


def test_demo_mode_mismatch_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(exchange_mode="paper", trading_mode="PAPER"))
    assert not d.approved and d.reason == "mode_not_demo_futures"


def test_live_trading_enabled_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(live_trading_enabled=True))
    assert not d.approved and d.reason == "live_trading_enabled_must_be_false"


def test_validation_schedule_drift_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(runtime_guardrails_intact=False))
    assert not d.approved and d.reason == "runtime_guardrails_drift"


def test_notional_cap_missing_blocks():
    d = evaluate_auto_approval(_cfg(max_notional_usdt=0.0), _inputs())
    assert not d.approved and d.reason == "notional_cap_missing_or_nonpositive"


def test_hawk_stale_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(posture=_ready_posture(hawk_stale=True)))
    assert not d.approved and d.reason == "hawk_read_stale"


def test_hawk_gate_not_passed_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(posture=_ready_posture(gate_passed=False)))
    assert not d.approved and d.reason == "hawk_gate_not_passed"


def test_hawk_neutral_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(posture=_ready_posture(majority="NEUTRAL")))
    assert not d.approved and d.reason == "hawk_no_directional_majority"


def test_ready_not_confirmed_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(ready_confirmations=1))
    assert not d.approved and d.reason == "ready_not_confirmed"


def test_exchange_not_flat_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(exchange_flat=False))
    assert not d.approved and d.reason == "exchange_not_flat"


def test_max_open_positions_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(open_positions=1))
    assert not d.approved and d.reason == "max_open_positions"


def test_daily_cap_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(auto_orders_today=1))
    assert not d.approved and d.reason == "daily_order_cap_reached"


def test_cooldown_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(last_auto_order_at=NOW - timedelta(minutes=10)))
    assert not d.approved and d.reason == "cooldown_active"


def test_consecutive_loss_ack_required_blocks():
    d = evaluate_auto_approval(
        _cfg(), _inputs(consecutive_loss_block_armed=True, consecutive_loss_ack_present=False)
    )
    assert not d.approved and d.reason == "consecutive_loss_ack_required"


def test_consecutive_loss_with_ack_passes():
    d = evaluate_auto_approval(
        _cfg(), _inputs(consecutive_loss_block_armed=True, consecutive_loss_ack_present=True)
    )
    assert d.approved


def test_sage_precheck_failed_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(sage_precheck=False))
    assert not d.approved and d.reason == "sage_precheck_failed"


def test_preflight_precheck_failed_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(preflight_precheck=False))
    assert not d.approved and d.reason == "preflight_precheck_failed"


def test_bearish_majority_yields_short():
    d = evaluate_auto_approval(_cfg(), _inputs(posture=_ready_posture(majority="BEARISH")))
    assert d.approved and d.direction == "SHORT"


def test_multiple_ready_symbols_blocks():
    d = evaluate_auto_approval(_cfg(), _inputs(posture=_ready_posture(ready_symbols=2)))
    assert not d.approved and d.reason == "no_single_ready_symbol"


def test_no_live_order_path_in_policy_module():
    # The policy module must carry no exchange/adapter/order-placement import surface.
    from pathlib import Path

    import app.services.demo_auto_approval as mod

    src = Path(mod.__file__).read_text()
    for forbidden in (
        "ccxt",
        "create_order",
        "place_order",
        "binance",
        "_demo_execute",
        "execute_proposal",
    ):
        assert forbidden not in src, f"policy module unexpectedly references {forbidden!r}"
