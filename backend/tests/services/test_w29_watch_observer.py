"""Phase W31A — read-only W29 Watch observer service tests.

Covers:
  * observe_once logs an advisory snapshot on HOLD and returns the compact summary.
  * observe_once flags READY_OWNER_APPROVAL_REQUIRED on READY but takes no other action.
  * the summary echoes the read-only hard safety fields verbatim.
  * default-symbols passthrough vs explicit symbols.
  * static read-only proof: the observer module imports/calls no order or dispatch code.

These tests never place an order, never dispatch a run, never create a risk_ack, and
never mutate validation_only. The watch is fully mocked, so no real/demo/live exchange
call is made.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services import w29_watch_observer as obs
from app.services.hawk_condition_watch import HawkConditionWatch

# ── Synthetic posture payloads (shape mirrors HawkConditionWatch.evaluate output) ──


def _posture(overall: str, action: str) -> dict:
    return {
        "generated_at": "2026-06-22T16:00:00+00:00",
        "project_id": "288bc95a-b4da-46e7-bdfa-b5630233f586",
        "overall_posture": overall,
        "recommended_action": action,
        "candidates": [
            {"symbol": "BTCUSDT", "posture": "WATCH_ONLY", "reasons": ["x"]},
            {"symbol": "ETHUSDT", "posture": "NOT_READY", "reasons": ["y"]},
        ],
        "order_capable": False,
        "dispatch_capable": False,
        "approval_required_for_retry": True,
        "validation_only_unchanged": True,
    }


def _patch_watch(monkeypatch, posture: dict) -> AsyncMock:
    """Replace HawkConditionWatch in the observer module with a fake returning ``posture``.

    Returns the evaluate AsyncMock so callers can assert how it was invoked.
    """
    evaluate = AsyncMock(return_value=posture)
    fake_instance = MagicMock()
    fake_instance.evaluate = evaluate
    fake_cls = MagicMock(return_value=fake_instance)
    monkeypatch.setattr(obs, "HawkConditionWatch", fake_cls)
    return evaluate


@pytest.mark.anyio
async def test_observe_once_hold_logs_snapshot_only(monkeypatch, caplog):
    _patch_watch(monkeypatch, _posture("HOLD", "WATCH_BTC"))
    with caplog.at_level(logging.INFO, logger=obs.__name__):
        summary = await obs.observe_once(MagicMock(), project_id=uuid4())

    assert summary["overall_posture"] == "HOLD"
    assert summary["recommended_action"] == "WATCH_BTC"
    assert summary["candidates"] == [
        {"symbol": "BTCUSDT", "posture": "WATCH_ONLY"},
        {"symbol": "ETHUSDT", "posture": "NOT_READY"},
    ]
    # An advisory snapshot line was emitted; the READY owner-approval flag was NOT.
    assert any(obs.LOG_MARKER in r.message for r in caplog.records)
    assert not any("READY_OWNER_APPROVAL_REQUIRED" in r.getMessage() for r in caplog.records)


@pytest.mark.anyio
async def test_observe_once_ready_flags_owner_approval(monkeypatch, caplog):
    _patch_watch(monkeypatch, _posture("READY", "OWNER_APPROVAL_REQUIRED"))
    with caplog.at_level(logging.INFO, logger=obs.__name__):
        summary = await obs.observe_once(MagicMock(), project_id=uuid4())

    assert summary["overall_posture"] == "READY"
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("READY_OWNER_APPROVAL_REQUIRED" in r.getMessage() for r in warnings)


@pytest.mark.anyio
async def test_observe_once_summary_carries_read_only_safety_fields(monkeypatch):
    _patch_watch(monkeypatch, _posture("HOLD", "WATCH_BTC"))
    summary = await obs.observe_once(MagicMock(), project_id=uuid4())
    assert summary["order_capable"] is False
    assert summary["dispatch_capable"] is False
    assert summary["approval_required_for_retry"] is True
    assert summary["validation_only_unchanged"] is True


@pytest.mark.anyio
async def test_observe_once_uses_default_symbols_when_none(monkeypatch):
    evaluate = _patch_watch(monkeypatch, _posture("NOT_READY", "HOLD"))
    await obs.observe_once(MagicMock(), project_id=uuid4())
    evaluate.assert_awaited_once()
    # No explicit symbol list → the watch service's own DEFAULT_SYMBOLS is used.
    assert "symbols" not in evaluate.await_args.kwargs


@pytest.mark.anyio
async def test_observe_once_passes_symbols_through(monkeypatch):
    evaluate = _patch_watch(monkeypatch, _posture("NOT_READY", "HOLD"))
    await obs.observe_once(MagicMock(), project_id=uuid4(), symbols=["BTCUSDT"])
    assert evaluate.await_args.kwargs["symbols"] == ["BTCUSDT"]


def test_watch_class_is_not_order_or_dispatch_capable():
    assert HawkConditionWatch.ORDER_CAPABLE is False
    assert HawkConditionWatch.DISPATCH_CAPABLE is False


# ── Static read-only proof ───────────────────────────────────────────────────

_FORBIDDEN_TOKENS = (
    "place_order",
    "create_order",
    "cancel_order",
    "close_position",
    "_dispatch_run",
    "send_task",
    "execute_run",
    "RunExecutor",
    "run_executor",
    "schedule_runner",
    "recovery_worker",
    "execution_service",
    "resume_approved",
    "resume_from_blocked",
    "risk_ack",
)

_ALLOWED_LOCAL_IMPORTS = {"app.services.hawk_condition_watch"}


def _observer_source() -> str:
    path = Path(obs.__file__)
    return path.read_text(encoding="utf-8")


def test_observer_module_has_no_order_or_dispatch_tokens():
    # Scan executable code only (drop the module docstring, which intentionally names the
    # capabilities the observer must NOT have).
    tree = ast.parse(_observer_source())
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    code = "\n".join(ast.unparse(node) for node in body)
    for token in _FORBIDDEN_TOKENS:
        assert token not in code, f"observer code unexpectedly references {token!r}"


def test_observer_module_only_imports_the_readonly_watch_from_app():
    tree = ast.parse(_observer_source())
    local_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("app.")
    }
    assert local_imports <= _ALLOWED_LOCAL_IMPORTS, (
        f"observer imports unexpected app modules: {local_imports - _ALLOWED_LOCAL_IMPORTS}"
    )
