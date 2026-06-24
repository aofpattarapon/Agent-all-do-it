"""Phase W31G — tests for the read-only guard-signal compute cores.

The pure ``compute_*`` functions carry the guard logic; they are tested directly here. The thin
async ``gather_*`` wrappers (DB/exchange I/O) are exercised by the runtime smoke, not unit tests.
"""

from __future__ import annotations

from app.services.demo_auto_approval_signals import (
    compute_consecutive_loss_armed,
    compute_exchange_flat,
    compute_runtime_guardrails_intact,
)

# --- exchange_flat ---------------------------------------------------------------------------


def test_exchange_flat_true_when_zero_position_and_no_orders():
    assert compute_exchange_flat([{"positionAmt": "0.0000"}], [], []) is True


def test_exchange_flat_false_with_open_position():
    assert compute_exchange_flat([{"positionAmt": "0.5"}], [], []) is False


def test_exchange_flat_false_with_open_order():
    assert compute_exchange_flat([{"positionAmt": "0"}], [{"orderId": 1}], []) is False


def test_exchange_flat_false_with_algo_order():
    assert compute_exchange_flat([{"positionAmt": "0"}], [], [{"algoId": 9}]) is False


def test_exchange_flat_false_on_unparseable_position_amt():
    # Unparseable size must not be read as flat (fail-closed).
    assert compute_exchange_flat([{"positionAmt": None}], [], []) is False


def test_exchange_flat_true_on_empty_inputs():
    assert compute_exchange_flat([], None, None) is True


# --- runtime_guardrails_intact ---------------------------------------------------------------


def _vo_ok() -> dict[str, str | None]:
    return {
        "Crypto Trade Pipeline — Auto 30m": "true",
        "Crypto Trade Pipeline — Auto 15m": "true",
    }


def test_guardrails_intact_when_all_good():
    assert (
        compute_runtime_guardrails_intact(
            mode_ok=True, validation_only_by_name=_vo_ok(), order_cron_enabled=[False, False]
        )
        is True
    )


def test_guardrails_drift_when_mode_not_ok():
    assert (
        compute_runtime_guardrails_intact(
            mode_ok=False, validation_only_by_name=_vo_ok(), order_cron_enabled=[False]
        )
        is False
    )


def test_guardrails_drift_when_validation_only_off():
    vo = _vo_ok()
    vo["Crypto Trade Pipeline — Auto 30m"] = "false"
    assert (
        compute_runtime_guardrails_intact(
            mode_ok=True, validation_only_by_name=vo, order_cron_enabled=[False]
        )
        is False
    )


def test_guardrails_drift_when_validation_only_missing():
    # A missing validation_only key (None) must fail closed.
    assert (
        compute_runtime_guardrails_intact(
            mode_ok=True,
            validation_only_by_name={"Crypto Trade Pipeline — Auto 30m": "true"},
            order_cron_enabled=[False],
        )
        is False
    )


def test_guardrails_drift_when_order_cron_enabled():
    assert (
        compute_runtime_guardrails_intact(
            mode_ok=True, validation_only_by_name=_vo_ok(), order_cron_enabled=[False, True]
        )
        is False
    )


# --- consecutive_loss_armed ------------------------------------------------------------------


def test_loss_armed_when_recent_all_loss():
    assert compute_consecutive_loss_armed(["LOSS", "LOSS", "LOSS"], 3) is True


def test_loss_not_armed_when_a_win_present():
    assert compute_consecutive_loss_armed(["LOSS", "WIN", "LOSS"], 3) is False


def test_loss_not_armed_when_too_few_trades():
    assert compute_consecutive_loss_armed(["LOSS", "LOSS"], 3) is False


def test_loss_not_armed_on_empty_history():
    assert compute_consecutive_loss_armed([], 3) is False
