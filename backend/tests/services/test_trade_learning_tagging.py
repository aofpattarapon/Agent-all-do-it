"""Phase 6.16.W30I — Lesson tagging fidelity (timeframe / direction / outcome / market / workflow).

Implements the W30H tagging plan:
  * ``record_lesson`` now writes additive **namespaced** facet tags
    (``symbol:`` / ``outcome:`` / ``direction:`` / ``timeframe:`` / ``market:`` / ``workflow:``)
    ALONGSIDE the legacy bare tags (``trade_lesson`` / ``<SYMBOL>`` / ``loss`` / ``win``).
  * Missing facets become an explicit ``:unknown`` sentinel — never fabricated.
  * High-cardinality identifiers stay in the Markdown ``lesson-meta`` block, never as tags.
  * ``get_relevant_lessons`` gains optional facet filters: broad mode never hides legacy
    lessons; ``strict=True`` requires the namespaced tag.

These are pure unit tests with in-memory fakes. No real / demo / testnet / live order is placed,
no schedule is touched, no workflow is run. A lesson remains ADVISORY context only — retrieval
metadata carries no approval / risk_ack / validation_only / order / execution / gate flag.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.trade_learning_service import (
    TradeLearningService,
    _build_lesson_content,
    _build_lesson_tags,
    _derive_workflow_timeframe,
    _norm_direction,
    _norm_market,
    _norm_timeframe,
    _norm_workflow,
)

_SVC_MOD = "app.services.trade_learning_service"


# ── normalisation helpers ────────────────────────────────────────────────────────────────────────


def test_norm_direction_maps_aliases_and_defaults_to_unknown() -> None:
    assert _norm_direction("LONG") == "long"
    assert _norm_direction("buy") == "long"
    assert _norm_direction("Short") == "short"
    assert _norm_direction("sell") == "short"
    assert _norm_direction(None) == "unknown"
    assert _norm_direction("sideways") == "unknown"


def test_norm_timeframe_only_accepts_known_intervals() -> None:
    assert _norm_timeframe("30m") == "30m"
    assert _norm_timeframe("1H") == "1h"
    assert _norm_timeframe(None) == "unknown"
    assert _norm_timeframe("banana") == "unknown"


def test_norm_market_and_workflow_normalise_or_unknown() -> None:
    assert _norm_market("Futures") == "futures"
    assert _norm_market("usdm_futures") == "futures"
    assert _norm_market("spot") == "spot"
    assert _norm_market(None) == "unknown"
    assert _norm_workflow("auto_30m") == "auto_30m"
    assert _norm_workflow("Auto 15m") == "auto_15m"
    assert _norm_workflow("manual") == "manual"
    assert _norm_workflow("") == "unknown"


def test_derive_workflow_timeframe_is_grounded_not_guessed() -> None:
    assert _derive_workflow_timeframe("Crypto Trade Pipeline — Auto 30m") == ("auto_30m", "30m")
    assert _derive_workflow_timeframe("Crypto Trade Pipeline — Auto 15m") == ("auto_15m", "15m")
    # a named-but-non-auto pipeline → manual kind, timeframe NOT fabricated
    assert _derive_workflow_timeframe("Crypto Trade Pipeline — Proposal to Execution") == ("manual", "unknown")
    assert _derive_workflow_timeframe(None) == ("unknown", "unknown")


# ── tag builder ───────────────────────────────────────────────────────────────────────────────────


def test_build_lesson_tags_emits_legacy_and_namespaced_tags() -> None:
    tags = _build_lesson_tags("BTCUSDT", -1.2, "long", "30m", "futures", "auto_30m")
    # legacy bare tags (backward compatibility)
    assert "trade_lesson" in tags
    assert "BTCUSDT" in tags
    assert "loss" in tags
    # additive namespaced facets
    assert "symbol:BTCUSDT" in tags
    assert "outcome:loss" in tags
    assert "direction:long" in tags
    assert "timeframe:30m" in tags
    assert "market:futures" in tags
    assert "workflow:auto_30m" in tags


def test_build_lesson_tags_uses_unknown_for_missing_facets() -> None:
    tags = _build_lesson_tags("ethusdt", 0.8, None, None, None, None)
    assert "win" in tags and "outcome:win" in tags
    assert "symbol:ETHUSDT" in tags  # symbol upper-cased per spec
    assert "direction:unknown" in tags
    assert "timeframe:unknown" in tags
    assert "market:unknown" in tags
    assert "workflow:unknown" in tags


def test_build_lesson_tags_are_deduplicated() -> None:
    tags = _build_lesson_tags("BTCUSDT", -1.0, "long", "30m", "futures", "auto_30m")
    assert len(tags) == len(set(tags))


def test_build_lesson_tags_strategy_optional_and_omitted_when_falsy() -> None:
    assert not any(t.startswith("strategy:") for t in _build_lesson_tags("BTCUSDT", -1.0, "long", "30m", "futures", "auto_30m"))
    with_strategy = _build_lesson_tags("BTCUSDT", -1.0, "long", "30m", "futures", "auto_30m", strategy="HAWK_SAGE")
    assert "strategy:hawk_sage" in with_strategy


# ── content / lesson-meta block ─────────────────────────────────────────────────────────────────


def test_build_lesson_content_has_machine_readable_lesson_meta_block() -> None:
    trade_id = uuid4()
    content = _build_lesson_content(
        trade_id=trade_id,
        symbol="BTCUSDT",
        pattern="range",
        agent_votes={"hawk_trend": "BUY"},
        outcome="SL",
        pnl_pct=-1.5,
        error_summary="stopped out",
        direction="short",
        timeframe="30m",
        market="futures",
        workflow="auto_30m",
    )
    assert "```lesson-meta" in content
    block = content.split("```lesson-meta", 1)[1].split("```", 1)[0].strip()
    meta = json.loads(block)
    assert meta["direction"] == "short"
    assert meta["timeframe"] == "30m"
    assert meta["market"] == "futures"
    assert meta["workflow"] == "auto_30m"
    assert meta["outcome"] == "loss"
    assert meta["close_reason"] == "SL"
    # high-cardinality identifier lives in content, NOT in the tag list
    assert str(trade_id) in content
    assert str(trade_id) not in _build_lesson_tags("BTCUSDT", -1.5, "short", "30m", "futures", "auto_30m")


# ── record_lesson persistence ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_record_lesson_persists_additive_tags(tmp_path) -> None:
    create = AsyncMock()
    with (
        patch(f"{_SVC_MOD}.knowledge_repo.create", create),
        patch(f"{_SVC_MOD}.project_vault_dir", return_value=tmp_path),
    ):
        svc = TradeLearningService(AsyncMock())
        await svc.record_lesson(
            project_id=uuid4(),
            trade_id=uuid4(),
            error_summary="stopped out",
            symbol="BTCUSDT",
            pattern="range",
            agent_votes={},
            outcome="SL",
            pnl_pct=-2.0,
            direction="short",
            timeframe="30m",
            market_type="futures",
            workflow="auto_30m",
        )
    _, kwargs = create.call_args
    tags = kwargs["tags"]
    assert {"trade_lesson", "BTCUSDT", "loss"} <= set(tags)  # legacy preserved
    assert {"symbol:BTCUSDT", "outcome:loss", "direction:short", "timeframe:30m", "market:futures", "workflow:auto_30m"} <= set(tags)
    assert kwargs["source_type"] == "trade_lesson"


@pytest.mark.anyio
async def test_record_lesson_defaults_to_unknown_tags(tmp_path) -> None:
    create = AsyncMock()
    with (
        patch(f"{_SVC_MOD}.knowledge_repo.create", create),
        patch(f"{_SVC_MOD}.project_vault_dir", return_value=tmp_path),
    ):
        svc = TradeLearningService(AsyncMock())
        await svc.record_lesson(
            project_id=uuid4(),
            trade_id=uuid4(),
            error_summary="x",
            symbol="SOLUSDT",
            pattern="p",
            agent_votes={},
            outcome="SL",
            pnl_pct=-1.0,
        )
    _, kwargs = create.call_args
    tags = set(kwargs["tags"])
    assert {"direction:unknown", "timeframe:unknown", "market:unknown", "workflow:unknown"} <= tags


# ── reflect_and_record passes the grounded direction ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_reflect_and_record_passes_direction_and_market() -> None:
    journal = SimpleNamespace(
        agent_votes={}, original_thesis="thesis", entry_price=1.0, exit_price=2.0,
        holding_time_minutes=10, what_happened="x", what_worked=None, mistakes=None,
        improvement=None, post_review_md=None,
    )
    db = SimpleNamespace(get=AsyncMock(return_value=journal), flush=AsyncMock())
    closed = SimpleNamespace(
        journal_id=uuid4(), position_id=uuid4(), symbol="BTCUSDT", direction="short",
        result="LOSS", realized_pnl=-5.0, realized_pnl_pct=-1.5, close_reason="SL",
    )
    spy = AsyncMock()
    with (
        patch(f"{_SVC_MOD}.agent_config_repo.list_by_project", AsyncMock(return_value=([], 0))),
        patch(f"{_SVC_MOD}.os.getenv", return_value="futures"),
        patch.object(TradeLearningService, "record_lesson", spy),
    ):
        svc = TradeLearningService(db)  # type: ignore[arg-type]
        await svc.reflect_and_record(uuid4(), closed)  # type: ignore[arg-type]
    _, kwargs = spy.call_args
    assert kwargs["direction"] == "short"
    assert kwargs["market_type"] == "futures"


# ── trigger_post_trade_learning handles missing direction safely + derives workflow ──────────────


@pytest.mark.anyio
async def test_trigger_post_trade_learning_derives_workflow_and_tolerates_missing_direction() -> None:
    run = SimpleNamespace(
        runtime_summary={"symbol": "BTCUSDT"},  # no direction recorded
        input_payload_json={},
        error_text=None,
        workflow_id=uuid4(),
    )
    workflow = SimpleNamespace(name="Crypto Trade Pipeline — Auto 30m")
    db = SimpleNamespace(get=AsyncMock(return_value=workflow))
    spy = AsyncMock()
    with (
        patch(f"{_SVC_MOD}.run_repo.get_run_by_id", AsyncMock(return_value=run)),
        patch(f"{_SVC_MOD}.os.getenv", return_value="futures"),
        patch.object(TradeLearningService, "record_lesson", spy),
    ):
        svc = TradeLearningService(db)  # type: ignore[arg-type]
        await svc.trigger_post_trade_learning(uuid4(), uuid4(), pnl_pct=-1.2)
    _, kwargs = spy.call_args
    assert kwargs["direction"] is None  # missing → record_lesson will tag direction:unknown
    assert kwargs["timeframe"] == "30m"
    assert kwargs["workflow"] == "auto_30m"
    assert kwargs["market_type"] == "futures"


@pytest.mark.anyio
async def test_trigger_post_trade_learning_skips_on_win() -> None:
    spy = AsyncMock()
    with patch.object(TradeLearningService, "record_lesson", spy):
        svc = TradeLearningService(AsyncMock())
        await svc.trigger_post_trade_learning(uuid4(), uuid4(), pnl_pct=1.0)
    spy.assert_not_awaited()  # loss-only behaviour preserved


# ── retrieval: broad never hides legacy, strict requires namespaced tags ──────────────────────────


class _CapturingDB:
    def __init__(self, docs: list[object]) -> None:
        self._docs = docs
        self.last_stmt: object = None

    async def execute(self, stmt: object):
        self.last_stmt = stmt
        scalars = SimpleNamespace(all=lambda: list(self._docs))
        return SimpleNamespace(scalars=lambda: scalars)


def _doc(title: str, tags: list[str]) -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), title=title, content="body", tags=tags, source_type="trade_lesson", created_at=None)


def _sql(stmt: object) -> str:
    return str(stmt).lower()


@pytest.mark.anyio
async def test_default_retrieval_adds_no_facet_predicates() -> None:
    """The live pipeline passes no facets — SQL must stay the prior project+source_type shape."""
    db = _CapturingDB([])
    svc = TradeLearningService(db)  # type: ignore[arg-type]
    await svc.get_relevant_lessons(uuid4(), symbol=None)
    sql = _sql(db.last_stmt)
    assert "jsonb_path_exists" not in sql
    assert "source_type" in sql


@pytest.mark.anyio
async def test_symbol_filter_dual_matches_bare_and_namespaced() -> None:
    db = _CapturingDB([])
    svc = TradeLearningService(db)  # type: ignore[arg-type]
    await svc.get_relevant_lessons(uuid4(), symbol="BTCUSDT")
    sql = _sql(db.last_stmt)
    # several JSONB containment alternatives OR-ed together (bare + namespaced, both casings)
    assert sql.count("@>") >= 2
    assert " or " in sql


@pytest.mark.anyio
async def test_broad_facet_filter_uses_non_hiding_predicate() -> None:
    db = _CapturingDB([])
    svc = TradeLearningService(db)  # type: ignore[arg-type]
    await svc.get_relevant_lessons(uuid4(), direction="long")
    sql = _sql(db.last_stmt)
    # broad mode: match OR doc-lacks-this-facet → jsonb_path_exists guard present
    assert "jsonb_path_exists" in sql
    assert 'starts with "direction:"' in sql


@pytest.mark.anyio
async def test_strict_facet_filter_requires_namespaced_tag_only() -> None:
    db = _CapturingDB([])
    svc = TradeLearningService(db)  # type: ignore[arg-type]
    await svc.get_relevant_lessons(uuid4(), direction="long", timeframe="30m", strict=True)
    sql = _sql(db.last_stmt)
    # strict mode: pure containment, no non-hiding guard
    assert "jsonb_path_exists" not in sql
    assert "@>" in sql


@pytest.mark.anyio
async def test_retrieval_returns_advisory_shape_only() -> None:
    db = _CapturingDB([_doc("Trade Lesson: BTCUSDT SL", ["trade_lesson", "BTCUSDT", "loss", "direction:short"])])
    svc = TradeLearningService(db)  # type: ignore[arg-type]
    lessons = await svc.get_relevant_lessons(uuid4(), symbol="BTCUSDT")
    assert set(lessons[0]) == {"id", "title", "content", "tags", "created_at"}
    # advisory payload carries no gate/approval/order/execution flag
    for forbidden in ("approved", "risk_ack", "validation_only", "order", "execute", "gate_passed"):
        assert forbidden not in lessons[0]
