"""Phase 6.14.W14-impl — sage_approved persistence-guard hardening tests.

Verifies that save_trade_proposal persists a PENDING_APPROVAL proposal when SAGE
approval is signalled either at the top level OR nested under agent_vote_summary
(the W13 Auto-run output shape), while remaining fail-closed when approval is
missing or explicitly false at both locations.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.crypto_persistence import CryptoPersistenceService, ProposalValidationError


def _db_pass_path() -> MagicMock:
    """Order-independent DB mock for the save_trade_proposal success path.

    Every ``execute`` returns a result that resolves to: no market snapshot,
    no existing proposal (INSERT branch), zero hawk votes, and no news events.
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalar = MagicMock(return_value=0)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _ks_result(passed: bool = True, adjusted: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        passed=passed,
        blocked_reasons=[] if passed else ["BLOCK"],
        warnings=[],
        adjusted_position_size_usdt=adjusted,
        checks_run=["sl_required", "tp_required", "risk_reward", "risk_per_trade"],
        consecutive_loss_ack_used=False,
    )


def _w13_payload(**overrides: object) -> dict:
    """A valid SHORT proposal payload modelled on the W13 Auto run."""
    payload = {
        "agent": "crypto_trade_proposal",
        "symbol": "BTCUSDT",
        "direction": "SHORT",
        "entry_plan": {"primary_entry": 63024.8, "entry_zone_low": 62237.2, "entry_zone_high": 63024.8},
        "take_profit": [{"tp_level": 61274.4, "rr_ratio": 2.0, "size_pct": 50}],
        "stop_loss": 63900.0,
        "position_size_usdt": 50.0,
        "risk_reward": 4.0,
        "approval_status": "PENDING_APPROVAL",
    }
    payload.update(overrides)
    return payload


def _env(key: str, default: object = None) -> object:
    return {
        "MARKET_TYPE": "futures",
        "MIN_FUTURES_NOTIONAL_USDT": "50.0",
        "KILL_SWITCH_PROPOSAL_EXPIRY_MINUTES": "30",
    }.get(key, default)


# ── _is_sage_approved helper (pure, no DB) ────────────────────────────────────


def test_is_sage_approved_top_level_true() -> None:
    assert CryptoPersistenceService._is_sage_approved({"sage_approved": True}) is True


def test_is_sage_approved_nested_true() -> None:
    assert (
        CryptoPersistenceService._is_sage_approved(
            {"agent_vote_summary": {"sage_approved": True}}
        )
        is True
    )


def test_is_sage_approved_missing_everywhere_false() -> None:
    assert CryptoPersistenceService._is_sage_approved({"agent_vote_summary": {}}) is False
    assert CryptoPersistenceService._is_sage_approved({}) is False


def test_is_sage_approved_false_top_level_false() -> None:
    assert CryptoPersistenceService._is_sage_approved({"sage_approved": False}) is False


def test_is_sage_approved_false_nested_false() -> None:
    assert (
        CryptoPersistenceService._is_sage_approved(
            {"agent_vote_summary": {"sage_approved": False}}
        )
        is False
    )


def test_is_sage_approved_string_true_not_accepted() -> None:
    # Strict boolean only — boolean-like strings are NOT normalized to approval.
    assert CryptoPersistenceService._is_sage_approved({"sage_approved": "true"}) is False


# ── persistence success ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_top_level_sage_approved_persists() -> None:
    db = _db_pass_path()
    svc = CryptoPersistenceService(db=db)
    with (
        patch("app.services.crypto_persistence.os.getenv", side_effect=_env),
        patch("app.services.crypto_persistence.KillSwitch") as mock_ks,
    ):
        mock_ks.return_value.check = AsyncMock(return_value=_ks_result())
        result = await svc.save_trade_proposal(
            project_id=uuid4(),
            run_id=uuid4(),
            payload=_w13_payload(sage_approved=True),
        )
    assert result is not None
    assert result.status == "PENDING_APPROVAL"


@pytest.mark.anyio
async def test_nested_sage_approved_persists_w13_shape() -> None:
    """The W13 regression: sage_approved only under agent_vote_summary must persist."""
    db = _db_pass_path()
    svc = CryptoPersistenceService(db=db)
    project_id = uuid4()
    run_id = uuid4()
    with (
        patch("app.services.crypto_persistence.os.getenv", side_effect=_env),
        patch("app.services.crypto_persistence.KillSwitch") as mock_ks,
    ):
        mock_ks.return_value.check = AsyncMock(return_value=_ks_result())
        result = await svc.save_trade_proposal(
            project_id=project_id,
            run_id=run_id,
            payload=_w13_payload(agent_vote_summary={"sage_approved": True}),
        )
    assert result is not None
    assert result.status == "PENDING_APPROVAL"
    assert result.run_id == run_id
    assert result.project_id == project_id
    assert result.symbol == "BTCUSDT"
    assert result.direction == "SHORT"
    assert result.stop_loss == 63900.0
    assert result.position_size_usdt == 50.0
    assert result.entry_plan["primary_entry"] == 63024.8
    assert len(result.take_profit) >= 1
    db.add.assert_called()


# ── fail-closed ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_sage_approved_missing_everywhere_raises_surfaced_reason() -> None:
    svc = CryptoPersistenceService(db=MagicMock())
    payload = _w13_payload(agent_vote_summary={"majority_direction": "BEARISH"})
    payload.pop("sage_approved", None)
    with pytest.raises(ProposalValidationError, match="SAGE_NOT_APPROVED"):
        await svc.save_trade_proposal(project_id=uuid4(), run_id=uuid4(), payload=payload)


@pytest.mark.anyio
async def test_sage_approved_false_top_level_does_not_persist() -> None:
    svc = CryptoPersistenceService(db=MagicMock())
    with pytest.raises(ProposalValidationError, match="SAGE_NOT_APPROVED"):
        await svc.save_trade_proposal(
            project_id=uuid4(), run_id=uuid4(), payload=_w13_payload(sage_approved=False)
        )


@pytest.mark.anyio
async def test_sage_approved_false_nested_does_not_persist() -> None:
    svc = CryptoPersistenceService(db=MagicMock())
    payload = _w13_payload(agent_vote_summary={"sage_approved": False})
    payload.pop("sage_approved", None)
    with pytest.raises(ProposalValidationError, match="SAGE_NOT_APPROVED"):
        await svc.save_trade_proposal(project_id=uuid4(), run_id=uuid4(), payload=payload)
