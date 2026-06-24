"""Phase 6.14.W22E — project-configurable warmup-mode policy.

Covers the real production decision-makers used by the Auto winrate gate
(``app.services.warmup_policy``): ``normalize_warmup_mode``, ``resolve_warmup_mode``
(resolution order + fail-closed), and ``decide_warmup_action`` (the pure gate decision).

Safety contract proven here:
* the warmup gate calls ``_auto_execute_trade_proposal`` (i.e. can place an order) ONLY when
  ``decide_warmup_action`` returns ``"auto_execute"``;
* ``pending_approval`` and ``validation_only`` NEVER return ``"auto_execute"`` → no order;
* an invalid / missing / unreadable mode always fails closed to ``pending_approval`` and never
  silently becomes ``auto_execute``;
* the post-warmup winrate logic (``below_threshold``) is unchanged.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.repositories import app_setting_repo
from app.services.warmup_policy import (
    DEFAULT_WARMUP_MODE,
    decide_warmup_action,
    normalize_warmup_mode,
    resolve_warmup_mode,
    warmup_mode_key,
)

# ── in-memory app_settings store (mirrors test_consecutive_loss_ack) ─────────


class _FakeStore:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.raise_on_get = False

    async def get_value(self, db: object, key: str, default: str = "") -> str:
        if self.raise_on_get:
            raise RuntimeError("simulated app_settings read failure")
        return self.data.get(key, default)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    fake = _FakeStore()
    monkeypatch.setattr(app_setting_repo, "get_value", fake.get_value)
    return fake


# ── normalize_warmup_mode ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("auto_execute", "auto_execute"),
        ("pending_approval", "pending_approval"),
        ("validation_only", "validation_only"),
        ("  AUTO_EXECUTE  ", "auto_execute"),  # trimmed + case-insensitive
        ("Validation_Only", "validation_only"),
    ],
)
def test_normalize_accepts_valid_modes(value: str, expected: str) -> None:
    assert normalize_warmup_mode(value) == expected


@pytest.mark.parametrize("value", ["", "auto", "yolo", "execute", "approve", None, 123, {"x": 1}])
def test_normalize_rejects_invalid_values(value: object) -> None:
    assert normalize_warmup_mode(value) is None


# ── resolve_warmup_mode: resolution order ────────────────────────────────────


@pytest.mark.anyio
async def test_project_setting_wins_over_workflow_and_env(
    store: _FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = uuid4()
    store.data[warmup_mode_key(pid)] = "validation_only"
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "PIPELINE_WARMUP_MODE", "auto_execute")
    mode = await resolve_warmup_mode(None, pid, {"warmup_mode": "auto_execute"})  # type: ignore[arg-type]
    assert mode == "validation_only"


@pytest.mark.anyio
async def test_workflow_config_used_when_no_project_setting(store: _FakeStore) -> None:
    pid = uuid4()  # store empty → falls through to workflow config
    mode = await resolve_warmup_mode(None, pid, {"warmup_mode": "auto_execute"})  # type: ignore[arg-type]
    assert mode == "auto_execute"


@pytest.mark.anyio
async def test_env_default_used_when_no_project_or_workflow(
    store: _FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = uuid4()
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "PIPELINE_WARMUP_MODE", "auto_execute")
    mode = await resolve_warmup_mode(None, pid, {})  # type: ignore[arg-type]
    assert mode == "auto_execute"


@pytest.mark.anyio
async def test_hard_fallback_is_pending_approval(
    store: _FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = uuid4()
    import app.core.config as config_module

    # env absent/blank, no project setting, no workflow config → hard fallback.
    monkeypatch.setattr(config_module.settings, "PIPELINE_WARMUP_MODE", "")
    mode = await resolve_warmup_mode(None, pid, None)  # type: ignore[arg-type]
    assert mode == "pending_approval"
    assert DEFAULT_WARMUP_MODE == "pending_approval"


# ── resolve_warmup_mode: fail-closed ─────────────────────────────────────────


@pytest.mark.anyio
async def test_invalid_project_setting_fails_closed_not_to_env_auto(
    store: _FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A present-but-invalid project value must NOT fall through to an auto_execute env."""
    pid = uuid4()
    store.data[warmup_mode_key(pid)] = "garbage"
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "PIPELINE_WARMUP_MODE", "auto_execute")
    mode = await resolve_warmup_mode(None, pid, {"warmup_mode": "auto_execute"})  # type: ignore[arg-type]
    assert mode == "pending_approval"


@pytest.mark.anyio
async def test_invalid_workflow_config_fails_closed(
    store: _FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = uuid4()
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "PIPELINE_WARMUP_MODE", "auto_execute")
    mode = await resolve_warmup_mode(None, pid, {"warmup_mode": "nope"})  # type: ignore[arg-type]
    assert mode == "pending_approval"


@pytest.mark.anyio
async def test_invalid_env_falls_back_to_pending(
    store: _FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = uuid4()
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "PIPELINE_WARMUP_MODE", "bogus")
    mode = await resolve_warmup_mode(None, pid, {})  # type: ignore[arg-type]
    assert mode == "pending_approval"


@pytest.mark.anyio
async def test_db_read_error_fails_closed(
    store: _FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = uuid4()
    store.raise_on_get = True
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "PIPELINE_WARMUP_MODE", "auto_execute")
    mode = await resolve_warmup_mode(None, pid, {"warmup_mode": "auto_execute"})  # type: ignore[arg-type]
    assert mode == "pending_approval"


# ── decide_warmup_action: the pure gate decision ─────────────────────────────


def test_warmup_auto_execute_action() -> None:
    assert (
        decide_warmup_action(in_warmup=True, winrate_pass=False, warmup_mode="auto_execute")
        == "auto_execute"
    )


def test_warmup_pending_approval_action_never_executes() -> None:
    action = decide_warmup_action(in_warmup=True, winrate_pass=True, warmup_mode="pending_approval")
    assert action == "pending_approval"
    assert action != "auto_execute"  # winrate_pass must not override the warmup policy


def test_warmup_validation_only_action_never_executes() -> None:
    action = decide_warmup_action(in_warmup=True, winrate_pass=True, warmup_mode="validation_only")
    assert action == "validation_only"
    assert action != "auto_execute"


def test_warmup_unknown_mode_fails_closed_to_pending() -> None:
    # decide receives an already-validated mode in production, but defends anyway.
    action = decide_warmup_action(in_warmup=True, winrate_pass=True, warmup_mode="weird")  # type: ignore[arg-type]
    assert action == "pending_approval"
    assert action != "auto_execute"


def test_post_warmup_winrate_pass_auto_executes() -> None:
    # warmup_mode is irrelevant once past warmup — the winrate gate is unchanged.
    for mode in ("auto_execute", "pending_approval", "validation_only"):
        assert (
            decide_warmup_action(in_warmup=False, winrate_pass=True, warmup_mode=mode)  # type: ignore[arg-type]
            == "auto_execute"
        )


def test_post_warmup_winrate_fail_goes_below_threshold() -> None:
    for mode in ("auto_execute", "pending_approval", "validation_only"):
        assert (
            decide_warmup_action(in_warmup=False, winrate_pass=False, warmup_mode=mode)  # type: ignore[arg-type]
            == "below_threshold"
        )


def test_only_intended_cases_yield_auto_execute() -> None:
    """Exhaustive guard: 'auto_execute' (→ order) occurs ONLY in the two intended cases."""
    auto_cases = []
    for in_warmup in (True, False):
        for winrate_pass in (True, False):
            for mode in ("auto_execute", "pending_approval", "validation_only"):
                action = decide_warmup_action(
                    in_warmup=in_warmup,
                    winrate_pass=winrate_pass,
                    warmup_mode=mode,  # type: ignore[arg-type]
                )
                if action == "auto_execute":
                    auto_cases.append((in_warmup, winrate_pass, mode))
    # Exactly: warmup + auto_execute (any winrate), and post-warmup + winrate_pass (any mode).
    expected = {
        (True, True, "auto_execute"),
        (True, False, "auto_execute"),
        (False, True, "auto_execute"),
        (False, True, "pending_approval"),
        (False, True, "validation_only"),
    }
    assert set(auto_cases) == expected
