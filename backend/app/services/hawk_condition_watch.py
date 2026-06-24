"""Phase 6.14.W28L — Read-only HAWK condition watch.

A STRICTLY READ-ONLY advisory service. It helps the owner decide *when* a future
controlled DEMO retry may be worth requesting, by computing a
``READY`` / ``NOT_READY`` / ``HOLD`` posture from public read-only market data and
historical HAWK vote-gate pass context.

Hard safety contract (Phase 6.14.W28L):
    * READ-ONLY ONLY. This module never places, cancels, or modifies an exchange order.
    * It never dispatches, approves, resumes, rejects, or retries a run.
    * It never creates a risk_ack.
    * It never mutates workflow ``validation_only`` or any production schedule.
    * It never overrides or weakens the HAWK threshold and never changes HAWK prompts.
    * No code path here imports order execution, run dispatch, approval/resume,
      risk_ack creation, or validation_only mutation.

Output is ADVISORY ONLY. ``READY`` means "conditions may be more likely to produce a
HAWK directional majority — consider asking the owner for fresh approval." It is NOT a
trade recommendation. The wording deliberately avoids buy/sell/long/short/enter.

Every fresh order-capable controlled DEMO retry still requires a brand-new explicit
owner approval block — this watch never substitutes for that.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import case, func, select

from app.db.models.workflow import Run, RunStep
from app.services import indicators

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Default owner-approved candidate set (read-only; never auto-traded) ──
DEFAULT_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
)

# ── Readiness thresholds (from the W28K design; advisory only) ──
RANGE_READY_PCT = 4.0  # 24h range expansion gate for READY
RANGE_NOT_READY_PCT = 3.0  # below this is treated as flat/ranging → NOT_READY
CHANGE_READY_PCT = 1.5  # absolute 24h directional thrust gate
VOLUME_READY_RATIO = 1.2  # recent-vs-prior volume confirmation gate
VOLUME_BELOW_AVG_RATIO = 1.0  # at/under average volume counts as "below average"
RSI_BULL = 60.0
RSI_BEAR = 40.0
PASS_RATE_READY_PCT = 55.0  # historical HAWK gate pass rate sufficiency
MIN_PASS_SAMPLE = 5  # minimum historical HAWK gate runs to trust a pass rate
UPPER_THIRD_PCT = 66.67  # close in upper third → upside positioning
LOWER_THIRD_PCT = 33.33  # close in lower third → downside positioning
WICK_SPIKE_FRACTION = 0.6  # one candle spanning >= this fraction of 24h range = wick spike
STALE_HAWK_HOURS = 6.0  # a HAWK read older than this is "stale"

_CANDLE_INTERVAL = "1h"
_CANDLE_LIMIT = 48  # last 24 candles = 24h window; prior 24 = baseline for volume ratio

# Per-symbol posture values
READY = "READY"
NOT_READY = "NOT_READY"
WATCH_ONLY = "WATCH_ONLY"

# Overall posture values
OVERALL_READY = "READY"
OVERALL_NOT_READY = "NOT_READY"
OVERALL_HOLD = "HOLD"

# Data-quality values
DQ_FULL = "FULL"
DQ_PARTIAL = "PARTIAL"
DQ_MISSING = "MISSING"


@dataclass
class SymbolMetrics:
    """Read-only market metrics derived from public 1h klines."""

    change_24h_pct: float | None = None
    range_24h_pct: float | None = None
    position_in_range_pct: float | None = None
    volume_ratio: float | None = None
    rsi_14: float | None = None
    one_bar_wick_spike: bool = False
    candle_count: int = 0
    data_quality: str = DQ_MISSING


@dataclass
class HistoricalHawk:
    """Read-only historical HAWK vote-gate context for a symbol."""

    pass_rate_pct: float | None = None
    sample_size: int = 0
    latest_majority_direction: str | None = None
    latest_gate_passed: bool | None = None
    latest_age_hours: float | None = None
    latest_is_stale: bool | None = None


def compute_symbol_metrics(klines: list[list]) -> SymbolMetrics:
    """Compute read-only 24h directional metrics from public 1h klines.

    ``klines`` rows are Binance ``[open_time, open, high, low, close, volume, ...]``.
    The most recent 24 rows form the 24h window; the 24 rows before that form the
    volume baseline. Pure function — no DB, no network, no side effects.
    """
    rows = [k for k in (klines or []) if len(k) >= 6]
    if not rows:
        return SymbolMetrics(candle_count=0, data_quality=DQ_MISSING)

    window = rows[-24:]
    closes = [float(k[4]) for k in window]
    highs = [float(k[2]) for k in window]
    lows = [float(k[3]) for k in window]
    opens = [float(k[1]) for k in window]
    volumes = [float(k[5]) for k in window]

    metrics = SymbolMetrics(candle_count=len(rows))

    # Need a meaningful 24h window to call anything FULL.
    metrics.data_quality = DQ_FULL if len(window) >= 24 else DQ_PARTIAL

    high_24 = max(highs)
    low_24 = min(lows)
    first_open = opens[0]
    last_close = closes[-1]

    if first_open > 0:
        metrics.change_24h_pct = round((last_close - first_open) / first_open * 100.0, 4)
    if low_24 > 0:
        metrics.range_24h_pct = round((high_24 - low_24) / low_24 * 100.0, 4)
    span = high_24 - low_24
    if span > 0:
        metrics.position_in_range_pct = round((last_close - low_24) / span * 100.0, 4)

    # Volume ratio: recent 24h mean vs prior 24h mean (expansion confirmation).
    prior = rows[-48:-24]
    if prior:
        prior_vols = [float(k[5]) for k in prior]
        prior_mean = sum(prior_vols) / len(prior_vols)
        recent_mean = sum(volumes) / len(volumes) if volumes else 0.0
        if prior_mean > 0:
            metrics.volume_ratio = round(recent_mean / prior_mean, 4)

    # RSI over all available closes (richer than just the 24h window).
    metrics.rsi_14 = indicators.rsi([float(k[4]) for k in rows], 14)

    # One-bar wick spike: a single candle spanning most of the 24h range, which
    # inflates range_24h_pct without genuine multi-bar follow-through.
    if span > 0:
        widest = max(float(k[2]) - float(k[3]) for k in window)
        metrics.one_bar_wick_spike = bool(widest >= WICK_SPIKE_FRACTION * span)

    return metrics


def evaluate_symbol_posture(
    symbol: str,
    metrics: SymbolMetrics,
    hist: HistoricalHawk,
) -> dict:
    """Classify a single symbol into READY / NOT_READY / WATCH_ONLY (advisory).

    Pure function. READY requires ALL directional, volume, momentum and historical
    conditions to align; missing history can never reach READY. Wording is advisory
    and avoids buy/sell/long/short/enter.
    """
    reasons: list[str] = []

    # No usable market data → cannot assess.
    if metrics.data_quality == DQ_MISSING or metrics.range_24h_pct is None:
        reasons.append("market data unavailable; cannot assess conditions")
        posture = NOT_READY
        return _symbol_payload(symbol, posture, reasons, metrics, hist)

    change = metrics.change_24h_pct or 0.0
    rng = metrics.range_24h_pct or 0.0
    pos = metrics.position_in_range_pct
    vol = metrics.volume_ratio
    rsi = metrics.rsi_14

    direction_up = change > 0

    range_ok = rng >= RANGE_READY_PCT
    change_ok = abs(change) >= CHANGE_READY_PCT
    pos_ok = pos is not None and (
        (direction_up and pos >= UPPER_THIRD_PCT)
        or (not direction_up and pos <= LOWER_THIRD_PCT)
    )
    vol_ok = vol is not None and vol >= VOLUME_READY_RATIO
    rsi_ok = rsi is not None and (
        (direction_up and rsi > RSI_BULL) or (not direction_up and rsi < RSI_BEAR)
    )
    not_spike = not metrics.one_bar_wick_spike

    has_history = (
        hist.pass_rate_pct is not None and hist.sample_size >= MIN_PASS_SAMPLE
    )
    hist_ok = has_history and (hist.pass_rate_pct or 0.0) >= PASS_RATE_READY_PCT

    # Build advisory reasons.
    reasons.append(
        f"24h range {rng:.2f}% "
        + ("(expansion)" if range_ok else "(compressed)" if rng < RANGE_NOT_READY_PCT else "(moderate)")
    )
    reasons.append(
        f"24h change {change:+.2f}% "
        + ("(directional thrust)" if change_ok else "(near flat)")
    )
    if pos is not None:
        reasons.append(f"close at {pos:.0f}% of 24h range")
    if vol is not None:
        reasons.append(
            f"volume {vol:.2f}x prior 24h "
            + ("(confirmed)" if vol_ok else "(below average)" if vol <= VOLUME_BELOW_AVG_RATIO else "(soft)")
        )
    if rsi is not None:
        reasons.append(
            f"RSI {rsi:.0f} "
            + ("(outside neutral band)" if (rsi > RSI_BULL or rsi < RSI_BEAR) else "(neutral)")
        )
    if metrics.one_bar_wick_spike:
        reasons.append("range dominated by a single-bar wick spike (no follow-through)")
    if not has_history:
        reasons.append("insufficient historical HAWK pass data for this symbol")
    else:
        reasons.append(
            f"historical HAWK pass rate {hist.pass_rate_pct:.0f}% over {hist.sample_size} runs "
            + ("(sufficient)" if hist_ok else "(below sufficiency)")
        )
    if hist.latest_is_stale:
        reasons.append("latest HAWK read is stale; not used as live confirmation")

    # ── Classification ──
    if not has_history:
        # Never READY without trustworthy history; advise watch if conditions are at
        # least moderately directional, otherwise not ready.
        posture = WATCH_ONLY if rng >= RANGE_NOT_READY_PCT else NOT_READY
        reasons.append(
            "conditions may be more likely to produce a HAWK directional majority, "
            "but fresh owner approval and HAWK history are required before any retry"
            if posture == WATCH_ONLY
            else "flat/ranging and unproven; not a likely HAWK-majority window"
        )
        return _symbol_payload(symbol, posture, reasons, metrics, hist)

    if range_ok and change_ok and pos_ok and vol_ok and rsi_ok and hist_ok and not_spike:
        posture = READY
        reasons.append(
            "conditions may be more likely to produce a HAWK directional majority; "
            "fresh owner approval is required before any controlled DEMO retry"
        )
    elif rng < RANGE_NOT_READY_PCT:
        posture = NOT_READY
        reasons.append("flat/ranging conditions; HAWK majority unlikely")
    elif vol is not None and vol <= VOLUME_BELOW_AVG_RATIO:
        posture = NOT_READY
        reasons.append("volume at/below average; directional move unconfirmed")
    else:
        posture = WATCH_ONLY
        reasons.append(
            "partial directional signals only; conditions not yet confirmed for a likely "
            "HAWK majority. Fresh owner approval required before any retry"
        )

    return _symbol_payload(symbol, posture, reasons, metrics, hist)


def _symbol_payload(
    symbol: str,
    posture: str,
    reasons: list[str],
    metrics: SymbolMetrics,
    hist: HistoricalHawk,
) -> dict:
    latest_hawk_read = None
    if hist.latest_majority_direction is not None or hist.latest_gate_passed is not None:
        latest_hawk_read = {
            "majority_direction": hist.latest_majority_direction,
            "gate_passed": hist.latest_gate_passed,
            "age_hours": hist.latest_age_hours,
            "is_stale": hist.latest_is_stale,
        }
    return {
        "symbol": symbol,
        "posture": posture,
        "reasons": reasons,
        "24h_change_pct": metrics.change_24h_pct,
        "24h_range_pct": metrics.range_24h_pct,
        "position_in_range_pct": metrics.position_in_range_pct,
        "volume_ratio": metrics.volume_ratio,
        "rsi_14": metrics.rsi_14,
        "latest_hawk_read": latest_hawk_read,
        "historical_hawk_pass_rate": hist.pass_rate_pct,
        "historical_hawk_sample_size": hist.sample_size,
        "data_quality": metrics.data_quality,
    }


def evaluate_overall_posture(candidates: list[dict]) -> tuple[str, str]:
    """Roll per-symbol postures into an overall posture + advisory recommended action."""
    postures = [c.get("posture") for c in candidates]
    if READY in postures:
        return OVERALL_READY, "OWNER_APPROVAL_REQUIRED"
    if WATCH_ONLY in postures:
        watch_syms = [c["symbol"] for c in candidates if c.get("posture") == WATCH_ONLY]
        action = "WATCH_BTC" if "BTCUSDT" in watch_syms else "WATCH_ALT_SYMBOL"
        return OVERALL_HOLD, action
    return OVERALL_NOT_READY, "HOLD"


class HawkConditionWatch:
    """Read-only orchestrator for the HAWK condition watch.

    Construct with an ``AsyncSession`` for read-only historical/DB context, then call
    :meth:`evaluate`. The class exposes hard safety capability flags that are always
    ``False`` for ordering/dispatch — they are surfaced in the output and asserted by tests.
    """

    ORDER_CAPABLE = False
    DISPATCH_CAPABLE = False

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def evaluate(
        self,
        *,
        project_id: UUID,
        symbols: list[str] | tuple[str, ...] = DEFAULT_SYMBOLS,
        lookback_days: int | None = None,
    ) -> dict:
        """Produce the structured READY/NOT_READY/HOLD posture object (read-only)."""
        syms = [s.upper() for s in symbols]
        pass_rates = await self._fetch_pass_rates(syms, lookback_days)
        candidates: list[dict] = []
        for sym in syms:
            metrics = await self._fetch_metrics(sym)
            hist = await self._fetch_latest_hawk(sym, pass_rates.get(sym))
            candidates.append(evaluate_symbol_posture(sym, metrics, hist))

        overall, action = evaluate_overall_posture(candidates)
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "project_id": str(project_id),
            "overall_posture": overall,
            "recommended_action": action,
            "candidates": candidates,
            # ── Hard safety fields (always read-only) ──
            "order_capable": False,
            "dispatch_capable": False,
            "approval_required_for_retry": True,
            "validation_only_unchanged": True,
        }

    async def _fetch_metrics(self, symbol: str) -> SymbolMetrics:
        """Fetch public read-only klines and derive metrics. Never signs/orders."""
        # Imported lazily and locally so the module's import graph carries no
        # order/dispatch capability; get_klines is an unsigned public-API read.
        from app.agents.tools.exchange_tool import get_klines

        try:
            klines = await get_klines(symbol, interval=_CANDLE_INTERVAL, limit=_CANDLE_LIMIT)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("hawk_condition_watch: klines fetch failed for %s: %s", symbol, exc)
            klines = []
        return compute_symbol_metrics(klines)

    async def _fetch_pass_rates(
        self, symbols: list[str], lookback_days: int | None
    ) -> dict[str, tuple[int, int]]:
        """Historical HAWK vote-gate pass counts per symbol → {sym: (passed, total)}.

        Read-only aggregate over ``run_steps`` (hawk_vote gate) joined to ``runs`` for
        the symbol. No writes.
        """
        sym_col = Run.input_payload_json["symbol"].astext
        passed_col = RunStep.output_json["meta"]["gate_passed"].astext
        stmt = (
            select(
                sym_col.label("sym"),
                func.count().label("total"),
                func.sum(case((passed_col == "true", 1), else_=0)).label("passed"),
            )
            .select_from(RunStep)
            .join(Run, Run.id == RunStep.run_id)
            .where(RunStep.step_kind == "hawk_vote")
            .where(sym_col.in_(symbols))
            .group_by(sym_col)
        )
        if lookback_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
            stmt = stmt.where(RunStep.created_at >= cutoff)

        out: dict[str, tuple[int, int]] = {}
        try:
            rows = (await self._session.execute(stmt)).all()
            for sym, total, passed in rows:
                out[sym] = (int(passed or 0), int(total or 0))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("hawk_condition_watch: pass-rate query failed: %s", exc)
        return out

    async def _fetch_latest_hawk(
        self, symbol: str, pass_counts: tuple[int, int] | None
    ) -> HistoricalHawk:
        """Most recent HAWK vote-gate read for a symbol + pass-rate context. Read-only."""
        passed, total = pass_counts or (0, 0)
        pass_rate = round(100.0 * passed / total, 1) if total else None
        hist = HistoricalHawk(pass_rate_pct=pass_rate, sample_size=total)

        sym_col = Run.input_payload_json["symbol"].astext
        stmt = (
            select(
                RunStep.output_json["meta"]["majority_direction"].astext,
                RunStep.output_json["meta"]["gate_passed"].astext,
                RunStep.created_at,
            )
            .select_from(RunStep)
            .join(Run, Run.id == RunStep.run_id)
            .where(RunStep.step_kind == "hawk_vote")
            .where(sym_col == symbol)
            .order_by(RunStep.created_at.desc())
            .limit(1)
        )
        try:
            row = (await self._session.execute(stmt)).first()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("hawk_condition_watch: latest-hawk query failed: %s", exc)
            row = None

        if row is not None:
            direction, gate_passed, created_at = row
            hist.latest_majority_direction = direction
            hist.latest_gate_passed = (gate_passed == "true") if gate_passed is not None else None
            if created_at is not None:
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                age = (datetime.now(UTC) - created_at).total_seconds() / 3600.0
                hist.latest_age_hours = round(age, 2)
                hist.latest_is_stale = age > STALE_HAWK_HOURS
        return hist


# Convenience so callers/tests can serialize dataclasses uniformly.
def metrics_as_dict(metrics: SymbolMetrics) -> dict:
    return asdict(metrics)
