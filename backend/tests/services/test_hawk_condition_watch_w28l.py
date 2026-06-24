"""Phase 6.14.W28L — Read-only HAWK condition watch tests.

Covers:
  * Criteria unit tests (ranging→NOT_READY, trending+volume+history→READY, no-history,
    stale read, low-volume trend, high-pass-rate-but-weak, one-bar wick spike).
  * Safety tests (no order/dispatch/risk_ack/validation_only capability; hard safety
    fields in output; mocked orchestration touches no exchange/order code).

The watch is strictly read-only: these tests never place an order, never dispatch a run,
never create a risk_ack, and never mutate validation_only. Market data is synthetic and the
DB session is a fake, so no real/demo/live exchange call is made.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import hawk_condition_watch as hcw
from app.services.hawk_condition_watch import (
    HawkConditionWatch,
    HistoricalHawk,
    SymbolMetrics,
    compute_symbol_metrics,
    evaluate_overall_posture,
    evaluate_symbol_posture,
)

# ── Synthetic kline helpers ──────────────────────────────────────────────────


def _kline(o: float, h: float, lo: float, c: float, v: float) -> list:
    # Binance row: [open_time, open, high, low, close, volume, ...] (strings on the wire).
    return [0, str(o), str(h), str(lo), str(c), str(v)]


def _ranging_klines() -> list:
    """48 flat bars oscillating inside ~0.6% — a BTC-like ranging tape."""
    rows = []
    for i in range(48):
        c = 100.0 + (0.3 if i % 2 == 0 else -0.3)
        rows.append(_kline(100.0, c + 0.1, c - 0.1, c, 100.0))
    return rows


def _trending_klines(*, volume_expands: bool = True) -> list:
    """48 bars in a clean uptrend: >4% range, >1.5% change, close near top, RSI high."""
    rows = []
    for i in range(48):
        c = 94.0 + i * (12.0 / 47.0)  # 94 → 106 steadily
        o = c - 0.15
        h = c + 0.1
        lo = c - 0.25
        vol = (220.0 if volume_expands else 100.0) if i >= 24 else 100.0
        rows.append(_kline(o, h, lo, c, vol))
    return rows


def _wick_spike_klines() -> list:
    """Flat tape except one huge single-bar wick that inflates the 24h range."""
    rows = [_kline(100.0, 100.1, 99.9, 100.0, 100.0) for _ in range(47)]
    # One violent bar: low wick far below, close back near 100 (no follow-through).
    rows.append(_kline(100.0, 100.2, 94.0, 100.0, 400.0))
    return rows


_STRONG_HIST = HistoricalHawk(pass_rate_pct=85.0, sample_size=20)
_NO_HIST = HistoricalHawk(pass_rate_pct=None, sample_size=0)


# ── Criteria unit tests ──────────────────────────────────────────────────────


def test_ranging_btc_like_is_not_ready():
    metrics = compute_symbol_metrics(_ranging_klines())
    assert metrics.range_24h_pct is not None and metrics.range_24h_pct < hcw.RANGE_NOT_READY_PCT
    posture = evaluate_symbol_posture("BTCUSDT", metrics, _STRONG_HIST)
    assert posture["posture"] == hcw.NOT_READY


def test_trending_with_volume_and_history_is_ready():
    metrics = compute_symbol_metrics(_trending_klines(volume_expands=True))
    assert metrics.range_24h_pct >= hcw.RANGE_READY_PCT
    assert abs(metrics.change_24h_pct) >= hcw.CHANGE_READY_PCT
    assert metrics.volume_ratio >= hcw.VOLUME_READY_RATIO
    assert not metrics.one_bar_wick_spike
    posture = evaluate_symbol_posture("SOLUSDT", metrics, _STRONG_HIST)
    assert posture["posture"] == hcw.READY
    # Advisory wording only — no trade verbs.
    joined = " ".join(posture["reasons"]).lower()
    for verb in ("buy", "sell", "long", "short", "enter"):
        assert verb not in joined


def test_no_history_never_ready():
    metrics = compute_symbol_metrics(_trending_klines(volume_expands=True))
    posture = evaluate_symbol_posture("BNBUSDT", metrics, _NO_HIST)
    assert posture["posture"] in (hcw.NOT_READY, hcw.WATCH_ONLY)
    assert posture["posture"] != hcw.READY


def test_stale_read_alone_does_not_cause_ready():
    # Flat market + a stale (but historically passing) HAWK read must not be READY.
    metrics = compute_symbol_metrics(_ranging_klines())
    hist = HistoricalHawk(
        pass_rate_pct=90.0,
        sample_size=30,
        latest_majority_direction="BULLISH",
        latest_gate_passed=True,
        latest_age_hours=48.0,
        latest_is_stale=True,
    )
    posture = evaluate_symbol_posture("BTCUSDT", metrics, hist)
    assert posture["posture"] != hcw.READY
    assert posture["latest_hawk_read"]["is_stale"] is True


def test_low_volume_trend_does_not_cause_ready():
    metrics = compute_symbol_metrics(_trending_klines(volume_expands=False))
    assert metrics.volume_ratio is not None and metrics.volume_ratio < hcw.VOLUME_READY_RATIO
    posture = evaluate_symbol_posture("SOLUSDT", metrics, _STRONG_HIST)
    assert posture["posture"] != hcw.READY


def test_high_pass_rate_but_weak_current_data_is_not_ready():
    # Strong history but currently flat/ranging → must not recommend an owner-order path.
    metrics = compute_symbol_metrics(_ranging_klines())
    hist = HistoricalHawk(pass_rate_pct=96.0, sample_size=40)
    posture = evaluate_symbol_posture("HYPEUSDT", metrics, hist)
    assert posture["posture"] == hcw.NOT_READY
    overall, action = evaluate_overall_posture([posture])
    assert overall == hcw.OVERALL_NOT_READY
    assert action != "OWNER_APPROVAL_REQUIRED"


def test_one_bar_wick_spike_does_not_cause_ready():
    metrics = compute_symbol_metrics(_wick_spike_klines())
    assert metrics.one_bar_wick_spike is True
    posture = evaluate_symbol_posture("BTCUSDT", metrics, _STRONG_HIST)
    assert posture["posture"] != hcw.READY


def test_missing_market_data_is_not_ready():
    metrics = compute_symbol_metrics([])
    assert metrics.data_quality == hcw.DQ_MISSING
    posture = evaluate_symbol_posture("XRPUSDT", metrics, _STRONG_HIST)
    assert posture["posture"] == hcw.NOT_READY


# ── Overall rollup ───────────────────────────────────────────────────────────


def test_overall_ready_requires_owner_approval_action():
    ready = {"symbol": "SOLUSDT", "posture": hcw.READY}
    overall, action = evaluate_overall_posture(
        [{"symbol": "BTCUSDT", "posture": hcw.NOT_READY}, ready]
    )
    assert overall == hcw.OVERALL_READY
    assert action == "OWNER_APPROVAL_REQUIRED"


def test_overall_hold_watch_btc():
    overall, action = evaluate_overall_posture(
        [{"symbol": "BTCUSDT", "posture": hcw.WATCH_ONLY}]
    )
    assert overall == hcw.OVERALL_HOLD
    assert action == "WATCH_BTC"


def test_overall_hold_watch_alt_symbol():
    overall, action = evaluate_overall_posture(
        [
            {"symbol": "BTCUSDT", "posture": hcw.NOT_READY},
            {"symbol": "SOLUSDT", "posture": hcw.WATCH_ONLY},
        ]
    )
    assert overall == hcw.OVERALL_HOLD
    assert action == "WATCH_ALT_SYMBOL"


# ── Safety tests ─────────────────────────────────────────────────────────────


_FORBIDDEN_CALL_NAMES = {
    # order execution / cancel
    "place_market_order",
    "place_limit_order",
    "place_stop_market_order",
    "place_take_profit_market_order",
    "place_algo_stop_market_order",
    "place_algo_take_profit_market_order",
    "cancel_order",
    "cancel_algo_order",
    "cancel_all_open_orders",
    "set_leverage",
    # execution / dispatch / approval / resume
    "execute_trade",
    "_run_exchange_execute",
    "_auto_execute_trade_proposal",
    "_promote_warmup_proposal",
    "resume_approved",
    "dispatch_run",
    "enqueue_run",
    # risk_ack mutation
    "create_risk_ack",
    "consume_risk_ack",
}


def _watch_ast() -> ast.Module:
    src = Path(hcw.__file__).read_text()
    return ast.parse(src)


def test_watch_module_does_not_call_order_or_dispatch_or_risk_ack():
    tree = _watch_ast()
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                called.add(fn.attr)
            elif isinstance(fn, ast.Name):
                called.add(fn.id)
    offenders = called & _FORBIDDEN_CALL_NAMES
    assert not offenders, f"watch must not call order/dispatch/risk_ack APIs: {offenders}"


def test_watch_module_does_not_import_forbidden_names():
    tree = _watch_ast()
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
    offenders = imported & _FORBIDDEN_CALL_NAMES
    assert not offenders, f"watch must not import order/dispatch/risk_ack APIs: {offenders}"


def test_watch_module_does_not_assign_validation_only():
    tree = _watch_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute):
                    assert target.attr != "validation_only", "watch must not mutate validation_only"
        if isinstance(node, ast.keyword):
            # e.g. update(validation_only=...) style keyword mutation
            assert node.arg != "validation_only", "watch must not set validation_only"


def test_capability_flags_are_false():
    assert HawkConditionWatch.ORDER_CAPABLE is False
    assert HawkConditionWatch.DISPATCH_CAPABLE is False


def _fake_session():
    """AsyncSession stub: execute() returns a result with empty .all()/None .first()."""
    result = AsyncMock()
    result.all = lambda: []
    result.first = lambda: None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.anyio
async def test_evaluate_output_has_hard_safety_fields(monkeypatch):
    import app.agents.tools.exchange_tool as exchange_tool

    monkeypatch.setattr(
        exchange_tool, "get_klines", AsyncMock(return_value=_ranging_klines())
    )

    watch = HawkConditionWatch(_fake_session())
    out = await watch.evaluate(project_id=uuid4(), symbols=["BTCUSDT", "ETHUSDT"])

    assert out["order_capable"] is False
    assert out["dispatch_capable"] is False
    assert out["approval_required_for_retry"] is True
    assert out["validation_only_unchanged"] is True
    assert out["overall_posture"] in (hcw.OVERALL_READY, hcw.OVERALL_NOT_READY, hcw.OVERALL_HOLD)
    assert "generated_at" in out
    assert len(out["candidates"]) == 2
    for c in out["candidates"]:
        assert set(c).issuperset(
            {
                "symbol",
                "posture",
                "reasons",
                "24h_change_pct",
                "24h_range_pct",
                "position_in_range_pct",
                "volume_ratio",
                "data_quality",
            }
        )


@pytest.mark.anyio
async def test_evaluate_does_not_construct_exchange_order_adapter(monkeypatch):
    # If the watch ever tried to place/cancel orders it would need the adapter's
    # signed order methods. Patch get_klines and assert the adapter ordering methods
    # are never touched during a full evaluate().
    import app.agents.tools.exchange_tool as exchange_tool

    monkeypatch.setattr(
        exchange_tool, "get_klines", AsyncMock(return_value=_trending_klines())
    )

    from app.crypto.exchanges import binance_futures_adapter as bfa

    placed = AsyncMock(side_effect=AssertionError("order method must not be called"))
    for name in (
        "place_market_order",
        "place_stop_market_order",
        "place_take_profit_market_order",
        "cancel_order",
        "cancel_algo_order",
    ):
        monkeypatch.setattr(bfa.BinanceFuturesAdapter, name, placed, raising=True)

    watch = HawkConditionWatch(_fake_session())
    out = await watch.evaluate(project_id=uuid4(), symbols=["SOLUSDT"])
    assert out["order_capable"] is False


def test_default_symbols_are_owner_approved_set():
    assert hcw.DEFAULT_SYMBOLS == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def test_metrics_as_dict_roundtrip():
    m = SymbolMetrics(change_24h_pct=1.0, data_quality=hcw.DQ_FULL)
    d = hcw.metrics_as_dict(m)
    assert d["change_24h_pct"] == 1.0 and d["data_quality"] == hcw.DQ_FULL
