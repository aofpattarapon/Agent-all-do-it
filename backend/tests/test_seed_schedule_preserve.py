"""Phase 2C-C.0 — seed schedule preserve fix.

Proves that re-seeding the crypto workflows is idempotent with respect to operator
enable/disable decisions: an existing schedule keeps its current ``enabled`` value, a newly
created schedule defaults to disabled unless it is the always-on Position Monitor, and the
manual/orphan disabler still turns stale cron rows off.

These tests exercise the shared decision helpers (used by BOTH the admin/API path
``seed_crypto_project`` and the CLI path ``_seed``) plus the orphan disabler — all in
isolation, with no real DB and no mutation of any live schedule state.
"""

import types
from unittest.mock import AsyncMock

import pytest

from app.commands.seed_crypto_workflow import (
    _POSITION_MONITOR_WORKFLOW_NAME,
    _disable_orphan_schedules,
    _seed_schedule_enabled_for_create,
    _seed_schedule_update_enabled,
)

# The five cron-triggered crypto workflows that carry a Schedule row.
_MARKET_WATCH = "Crypto Market Watch — Continuous Research"
_PROPOSAL_TO_EXECUTION = "Crypto Trade Pipeline — Proposal to Execution"
_POSITION_MONITOR = _POSITION_MONITOR_WORKFLOW_NAME
_PRIMARY_SCREENER = "Crypto Trade Screener — Primary 30m"
_SECONDARY_SCREENER = "Crypto Trade Screener — Secondary 15m"

_ORDER_CAPABLE_CRON = [
    _MARKET_WATCH,
    _PROPOSAL_TO_EXECUTION,
    _PRIMARY_SCREENER,
    _SECONDARY_SCREENER,
]


# ── UPDATE branch: preserve flag ON (default) never clobbers operator decisions ──


@pytest.mark.parametrize("workflow_name", _ORDER_CAPABLE_CRON)
def test_update_preserve_on_returns_none_for_order_capable(workflow_name: str) -> None:
    # None => "leave the existing enabled value untouched". A disabled Market Watch / Primary /
    # Secondary / Proposal-to-Execution therefore stays disabled across a reseed.
    assert _seed_schedule_update_enabled(workflow_name, preserve_enabled=True) is None


def test_update_preserve_on_returns_none_for_position_monitor() -> None:
    # Even the Position Monitor's value is preserved on update — a deliberate disable is kept.
    assert _seed_schedule_update_enabled(_POSITION_MONITOR, preserve_enabled=True) is None


def test_update_preserve_on_is_idempotent() -> None:
    # Reseeding twice yields the same "don't touch" decision both times.
    first = _seed_schedule_update_enabled(_MARKET_WATCH, preserve_enabled=True)
    second = _seed_schedule_update_enabled(_MARKET_WATCH, preserve_enabled=True)
    assert first is None and second is None


# ── UPDATE branch: preserve flag OFF restores legacy force-enable ──


@pytest.mark.parametrize("workflow_name", [*_ORDER_CAPABLE_CRON, _POSITION_MONITOR])
def test_update_preserve_off_forces_enabled(workflow_name: str) -> None:
    assert _seed_schedule_update_enabled(workflow_name, preserve_enabled=False) is True


# ── CREATE branch: safe defaults ──


@pytest.mark.parametrize("workflow_name", _ORDER_CAPABLE_CRON)
def test_create_preserve_on_defaults_order_capable_disabled(workflow_name: str) -> None:
    assert _seed_schedule_enabled_for_create(workflow_name, preserve_enabled=True) is False


def test_create_preserve_on_enables_position_monitor() -> None:
    assert _seed_schedule_enabled_for_create(_POSITION_MONITOR, preserve_enabled=True) is True


@pytest.mark.parametrize("workflow_name", [*_ORDER_CAPABLE_CRON, _POSITION_MONITOR])
def test_create_preserve_off_enables_everything(workflow_name: str) -> None:
    assert _seed_schedule_enabled_for_create(workflow_name, preserve_enabled=False) is True


# ── Live-schedule guarantee, expressed as the apply-to-existing-row contract ──


def _apply_update(existing_enabled: bool, workflow_name: str, *, preserve_enabled: bool) -> bool:
    """Mirror the seed update branch: build update_data, then resolve the row's final state."""
    override = _seed_schedule_update_enabled(workflow_name, preserve_enabled=preserve_enabled)
    return existing_enabled if override is None else override


@pytest.mark.parametrize("workflow_name", _ORDER_CAPABLE_CRON)
def test_disabled_row_stays_disabled_after_reseed(workflow_name: str) -> None:
    assert _apply_update(False, workflow_name, preserve_enabled=True) is False


def test_enabled_position_monitor_stays_enabled_after_reseed() -> None:
    assert _apply_update(True, _POSITION_MONITOR, preserve_enabled=True) is True


@pytest.mark.parametrize("workflow_name", _ORDER_CAPABLE_CRON)
def test_enabled_row_stays_enabled_after_reseed(workflow_name: str) -> None:
    # If an operator deliberately enabled a screener, a reseed must not flip it off either.
    assert _apply_update(True, workflow_name, preserve_enabled=True) is True


# ── Orphan disabler (manual workflows: Auto 30m / Auto 15m) still disables stale cron rows ──


class _FakeScalarResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self) -> "_FakeScalarResult":
        return self

    def all(self) -> list:
        return self._rows


class _FakeDB:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    async def execute(self, *_args, **_kwargs) -> _FakeScalarResult:
        return _FakeScalarResult(self._rows)


@pytest.mark.anyio
async def test_disable_orphan_schedules_disables_enabled_rows(monkeypatch) -> None:
    from uuid import uuid4

    import app.repositories.workflow as workflow_repo

    enabled_row = types.SimpleNamespace(enabled=True)
    db = _FakeDB([enabled_row])

    async def fake_update(_db, *, db_schedule, update_data) -> object:
        for field, value in update_data.items():
            setattr(db_schedule, field, value)
        return db_schedule

    monkeypatch.setattr(workflow_repo, "update_schedule", AsyncMock(side_effect=fake_update))

    disabled = await _disable_orphan_schedules(db, project_id=uuid4(), workflow_id=uuid4())

    assert disabled == 1
    assert enabled_row.enabled is False
