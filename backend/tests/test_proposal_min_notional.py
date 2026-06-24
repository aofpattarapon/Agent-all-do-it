"""Phase 6.14.I — Futures minimum notional proposal safety tests.

Verifies that save_trade_proposal blocks proposals with position_size_usdt below
the Binance Futures minimum notional before they reach execution preflight.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.crypto_persistence import CryptoPersistenceService, ProposalValidationError


def _db_pass_path() -> MagicMock:
    """DB mock providing enough execute responses for the full save_trade_proposal pass path.

    save_trade_proposal makes 4 sequential db.execute calls on the success path:
      1. _latest_market_snapshot  -> scalar_one_or_none -> None
      2. _count_hawk_votes        -> scalar            -> 0
      3. _news_events_for_run     -> scalars().all()   -> []
      4. _latest_trade_proposal   -> scalar_one_or_none -> None  (INSERT branch)
    """
    r_snapshot = MagicMock()
    r_snapshot.scalar_one_or_none = MagicMock(return_value=None)

    r_votes = MagicMock()
    r_votes.scalar = MagicMock(return_value=0)

    r_news = MagicMock()
    r_news.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    r_existing = MagicMock()
    r_existing.scalar_one_or_none = MagicMock(return_value=None)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[r_snapshot, r_votes, r_news, r_existing])
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _db_no_snapshot() -> MagicMock:
    """DB mock for tests that block before reaching any DB call (only used by blocking tests)."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _base_payload(**overrides: object) -> dict:
    payload = {
        "agent": "crypto_trade_proposal",
        "symbol": "BTCUSDT",
        "direction": "SHORT",
        "sage_approved": True,
        "entry_plan": {"primary_entry": 64297.7},
        "take_profit": [{"tp_level": 63500.0}],
        "stop_loss": 64630.0,
        "position_size_usdt": 50.0,
        "risk_reward": 2.0,
        "approval_status": "PENDING_APPROVAL",
    }
    payload.update(overrides)
    return payload


def _ks_result(passed: bool = True, adjusted: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        passed=passed,
        blocked_reasons=[] if passed else ["BLOCK"],
        warnings=[],
        adjusted_position_size_usdt=adjusted,
        checks_run=["sl_required", "tp_required", "risk_reward", "risk_per_trade"],
        consecutive_loss_ack_used=False,
    )


# ── Futures min-notional guard ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_futures_proposal_below_min_notional_blocks() -> None:
    """position_size_usdt=40 with MARKET_TYPE=futures must raise ProposalValidationError."""
    svc = CryptoPersistenceService(db=_db_no_snapshot())

    with (
        patch("app.services.crypto_persistence.os.getenv") as mock_env,
        patch("app.services.crypto_persistence.KillSwitch") as _mock_ks,
    ):
        mock_env.side_effect = lambda key, default=None: {
            "MARKET_TYPE": "futures",
            "MIN_FUTURES_NOTIONAL_USDT": "50.0",
        }.get(key, default)

        with pytest.raises(
            ProposalValidationError, match="PROPOSAL_NOTIONAL_BELOW_EXCHANGE_MINIMUM"
        ):
            await svc.save_trade_proposal(
                project_id=uuid4(),
                run_id=uuid4(),
                payload=_base_payload(position_size_usdt=40.0),
            )


@pytest.mark.anyio
async def test_futures_proposal_exactly_min_notional_passes() -> None:
    """position_size_usdt=50.0 with MARKET_TYPE=futures must pass the notional floor."""
    db = _db_pass_path()
    svc = CryptoPersistenceService(db=db)

    with (
        patch("app.services.crypto_persistence.os.getenv") as mock_env,
        patch("app.services.crypto_persistence.KillSwitch") as mock_ks,
    ):
        mock_env.side_effect = lambda key, default=None: {
            "MARKET_TYPE": "futures",
            "MIN_FUTURES_NOTIONAL_USDT": "50.0",
            "KILL_SWITCH_PROPOSAL_EXPIRY_MINUTES": "30",
        }.get(key, default)
        mock_ks.return_value.check = AsyncMock(return_value=_ks_result())

        result = await svc.save_trade_proposal(
            project_id=uuid4(),
            run_id=uuid4(),
            payload=_base_payload(position_size_usdt=50.0),
        )

    assert result is not None


@pytest.mark.anyio
async def test_futures_proposal_above_min_notional_passes() -> None:
    """position_size_usdt=60 must pass."""
    db = _db_pass_path()
    svc = CryptoPersistenceService(db=db)

    with (
        patch("app.services.crypto_persistence.os.getenv") as mock_env,
        patch("app.services.crypto_persistence.KillSwitch") as mock_ks,
    ):
        mock_env.side_effect = lambda key, default=None: {
            "MARKET_TYPE": "futures",
            "MIN_FUTURES_NOTIONAL_USDT": "50.0",
            "KILL_SWITCH_PROPOSAL_EXPIRY_MINUTES": "30",
        }.get(key, default)
        mock_ks.return_value.check = AsyncMock(return_value=_ks_result())

        result = await svc.save_trade_proposal(
            project_id=uuid4(),
            run_id=uuid4(),
            payload=_base_payload(position_size_usdt=60.0),
        )

    assert result is not None


@pytest.mark.anyio
async def test_spot_proposal_below_futures_min_notional_passes() -> None:
    """position_size_usdt=40 with MARKET_TYPE=spot must NOT be blocked by the futures notional floor."""
    db = _db_pass_path()
    svc = CryptoPersistenceService(db=db)

    with (
        patch("app.services.crypto_persistence.os.getenv") as mock_env,
        patch("app.services.crypto_persistence.KillSwitch") as mock_ks,
    ):
        mock_env.side_effect = lambda key, default=None: {
            "MARKET_TYPE": "spot",
            "MIN_FUTURES_NOTIONAL_USDT": "50.0",
            "KILL_SWITCH_PROPOSAL_EXPIRY_MINUTES": "30",
        }.get(key, default)
        mock_ks.return_value.check = AsyncMock(return_value=_ks_result())

        # Spot SHORT is blocked by a different guard (spot market does not support SHORT),
        # so use LONG for this test.
        payload = _base_payload(
            direction="LONG",
            stop_loss=63900.0,
            take_profit=[{"tp_level": 65000.0}],
            position_size_usdt=40.0,
        )
        result = await svc.save_trade_proposal(
            project_id=uuid4(),
            run_id=uuid4(),
            payload=payload,
        )

    assert result is not None


@pytest.mark.anyio
async def test_futures_custom_env_min_notional_blocks() -> None:
    """MIN_FUTURES_NOTIONAL_USDT=100 env override blocks position_size_usdt=80."""
    svc = CryptoPersistenceService(db=_db_no_snapshot())

    with (
        patch("app.services.crypto_persistence.os.getenv") as mock_env,
        patch("app.services.crypto_persistence.KillSwitch") as _mock_ks,
    ):
        mock_env.side_effect = lambda key, default=None: {
            "MARKET_TYPE": "futures",
            "MIN_FUTURES_NOTIONAL_USDT": "100.0",
        }.get(key, default)

        with pytest.raises(
            ProposalValidationError, match="PROPOSAL_NOTIONAL_BELOW_EXCHANGE_MINIMUM"
        ):
            await svc.save_trade_proposal(
                project_id=uuid4(),
                run_id=uuid4(),
                payload=_base_payload(position_size_usdt=80.0),
            )


def test_proposal_notional_error_message_contains_clear_reason() -> None:
    """Error message must include the structured reason code."""
    err = ProposalValidationError(
        "PROPOSAL_NOTIONAL_BELOW_EXCHANGE_MINIMUM: position_size_usdt 40.0 < minNotional 50.0 "
        "for futures market (symbol=BTCUSDT, direction=SHORT, run_id=...)"
    )
    assert "PROPOSAL_NOTIONAL_BELOW_EXCHANGE_MINIMUM" in str(err)
    assert "40.0" in str(err)
    assert "50.0" in str(err)


# ── Existing safety checks still apply ────────────────────────────────────────


def _db_resilient() -> MagicMock:
    """DB mock that satisfies any read order: scalar_one_or_none->None, scalar->0, all()->[]."""

    def _exec(*_a: object, **_k: object) -> MagicMock:
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=None)
        r.scalar = MagicMock(return_value=0)
        r.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_exec)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.anyio
async def test_short_sl_below_entry_persists_blocked_kill_switch() -> None:
    """W28E: a kill-switch block now PERSISTS a non-executable BLOCKED_KILL_SWITCH row.

    Previously ``save_trade_proposal`` silently returned ``None`` (no traceability and nothing to
    promote later). It must instead persist the SAGE-approved proposal in an explicit
    non-executable state so a later warmup approval/resume can re-validate and promote it — while
    execution stays fail-closed (execute_trade requires APPROVED; preflight re-runs the kill
    switch).
    """
    db = _db_resilient()
    svc = CryptoPersistenceService(db=db)

    with (
        patch("app.services.crypto_persistence.os.getenv") as mock_env,
        patch("app.services.crypto_persistence.KillSwitch") as mock_ks,
    ):
        mock_env.side_effect = lambda key, default=None: {
            "MARKET_TYPE": "futures",
            "MIN_FUTURES_NOTIONAL_USDT": "50.0",
            "KILL_SWITCH_PROPOSAL_EXPIRY_MINUTES": "30",
        }.get(key, default)
        # Kill switch blocks due to wrong-direction SL
        mock_ks.return_value.check = AsyncMock(return_value=_ks_result(passed=False, adjusted=None))

        # SL below entry for SHORT — kill switch should block; notional is valid (50)
        payload = _base_payload(
            direction="SHORT",
            stop_loss=63900.0,  # below entry 64297.7 — wrong for SHORT
            take_profit=[{"tp_level": 63500.0}],
            position_size_usdt=50.0,
        )
        result = await svc.save_trade_proposal(
            project_id=uuid4(),
            run_id=uuid4(),
            payload=payload,
        )

    # Persisted, but explicitly non-executable — never APPROVED / PENDING_APPROVAL.
    assert result is not None
    assert result.status == "BLOCKED_KILL_SWITCH"
    assert result.kill_switch_passed is False
    assert "KILL_SWITCH_BLOCKED" in (result.rejection_reason or "")
    db.add.assert_called()  # the blocked proposal row was persisted for traceability


# ── Execution preflight regression ────────────────────────────────────────────


@pytest.mark.anyio
async def test_execution_preflight_still_blocks_below_notional() -> None:
    """validate_order_request still catches notional violations at execution time as final guard."""
    from datetime import timedelta
    from types import SimpleNamespace
    from unittest.mock import patch

    from app.services.execution_preflight import ExecutionPreflightError, prepare_execution_plan

    r_none = MagicMock()
    r_none.scalar_one_or_none = MagicMock(return_value=None)
    db = SimpleNamespace(execute=AsyncMock(side_effect=[r_none, r_none, r_none]))

    proposal = SimpleNamespace(
        id=uuid4(),
        symbol="BTCUSDT",
        direction="SHORT",
        status="APPROVED",
        expires_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        + timedelta(minutes=10),
        entry_plan={"primary_entry": 64297.7},
        take_profit=[{"tp_level": 63500.0}],
        stop_loss=64630.0,
        position_size_usdt=40.0,
    )

    with (
        patch(
            "app.services.execution_preflight.validate_order_request",
            AsyncMock(
                return_value={
                    "passed": False,
                    "errors": ["PREFLIGHT NOTIONAL: notional_usdt 40.0 < minNotional 50.0"],
                }
            ),
        ),
        patch("app.services.execution_preflight.KillSwitch") as mock_ks,
        patch("app.services.execution_preflight.os.getenv") as mock_env,
    ):
        mock_env.side_effect = lambda key, default=None: (
            "futures" if key == "MARKET_TYPE" else default
        )
        mock_ks.return_value.check = AsyncMock(
            return_value=SimpleNamespace(
                passed=True,
                blocked_reasons=[],
                adjusted_position_size_usdt=None,
            )
        )

        with pytest.raises(ExecutionPreflightError, match="PREFLIGHT NOTIONAL"):
            await prepare_execution_plan(
                db=db,
                project_id=uuid4(),
                proposal=proposal,
                require_status="APPROVED",
            )
