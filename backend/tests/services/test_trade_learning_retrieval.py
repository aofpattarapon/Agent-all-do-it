"""Phase 6.16.W30B — Lesson retrieval fidelity + advisory-only safety.

Covers the W30A findings:
  * ``check_trade_lessons`` (a ``kb_search`` step) now HONORS ``source_type_filter`` by routing
    through the canonical ``TradeLearningService.get_relevant_lessons`` retrieval.
  * Retrieval is scoped to the requested ``source_type`` AND the run's symbol.
  * No-lessons / retrieval-error degrade to safe advisory output — never a failure, never a gate
    bypass.

These are pure unit tests with an in-memory fake DB. No real / demo / testnet / live order is
placed, no schedule is touched, no workflow is run. The whole point is that a lesson is ADVISORY
prompt text only: the returned step metadata carries no approval / risk_ack / validation_only /
order-param / execution flag, and the executor never lets retrieval mutate a gate outcome.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.run_executor import RunExecutor
from app.services.trade_learning_service import TradeLearningService


class _CapturingDB:
    """AsyncSession stand-in that records the statement and returns canned rows."""

    def __init__(self, docs: list[object]) -> None:
        self._docs = docs
        self.last_stmt: object = None

    async def execute(self, stmt: object):
        self.last_stmt = stmt
        scalars = SimpleNamespace(all=lambda: list(self._docs))
        return SimpleNamespace(scalars=lambda: scalars)


def _doc(title: str, tags: list[str], source_type: str = "trade_lesson") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        content=f"{title} body",
        tags=tags,
        source_type=source_type,
        created_at=None,
    )


def _sql(stmt: object) -> str:
    return str(stmt).lower()


# ── get_relevant_lessons fidelity ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_relevant_lessons_filters_by_source_type_and_symbol() -> None:
    db = _CapturingDB([_doc("Trade Lesson: BTCUSDT SL", ["trade_lesson", "BTCUSDT", "loss"])])
    svc = TradeLearningService(db)  # type: ignore[arg-type]

    lessons = await svc.get_relevant_lessons(uuid4(), symbol="BTCUSDT", source_type="trade_lesson")

    sql = _sql(db.last_stmt)
    assert "source_type" in sql  # source_type filter is applied (fixes dead config)
    assert "@>" in sql  # JSONB tag containment is applied for the symbol
    assert lessons[0]["title"] == "Trade Lesson: BTCUSDT SL"
    # additive shape used by the advisory formatter
    assert set(lessons[0]) >= {"id", "title", "content", "tags", "created_at"}


@pytest.mark.anyio
async def test_get_relevant_lessons_without_symbol_skips_tag_filter() -> None:
    db = _CapturingDB([])
    svc = TradeLearningService(db)  # type: ignore[arg-type]

    await svc.get_relevant_lessons(uuid4(), symbol=None, source_type="trade_lesson")

    sql = _sql(db.last_stmt)
    assert "source_type" in sql  # still source_type-scoped
    assert "@>" not in sql  # no symbol → no JSONB tag containment (safe project-wide fallback)


@pytest.mark.anyio
async def test_get_relevant_lessons_empty_is_safe_not_error() -> None:
    svc = TradeLearningService(_CapturingDB([]))  # type: ignore[arg-type]
    lessons = await svc.get_relevant_lessons(uuid4(), symbol="BTCUSDT")
    assert lessons == []  # empty list, not an exception


# ── _run_kb_search routing: source_type_filter is honored, output is advisory only ───────────────


def _executor() -> RunExecutor:
    return RunExecutor(db=AsyncMock())  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_kb_search_routes_filtered_step_through_lesson_retrieval() -> None:
    ex = _executor()
    project_id = uuid4()
    config = {"source_type_filter": "trade_lesson", "top_k": 5}
    context = {"input_payload": {"symbol": "btcusdt"}}  # lower-case → must be normalised

    spy = AsyncMock(
        return_value=[
            {"id": "d1", "title": "Trade Lesson: BTCUSDT SL", "content": "lost on a wick", "tags": []}
        ]
    )
    with patch.object(TradeLearningService, "get_relevant_lessons", spy):
        text, meta = await ex._run_kb_search(project_id, config, context)

    # routed with the declared source_type and the resolved, upper-cased symbol
    _, kwargs = spy.call_args
    assert kwargs["source_type"] == "trade_lesson"
    assert kwargs["symbol"] == "BTCUSDT"
    # advisory text + advisory metadata; NO gate/approval/order keys present
    assert "advisory only" in text.lower()
    assert meta["matches"] == 1
    assert meta["advisory"] is True
    assert meta["source_type_filter"] == "trade_lesson"
    for forbidden in ("approved", "risk_ack", "validation_only", "order", "execute", "gate_passed"):
        assert forbidden not in meta


@pytest.mark.anyio
async def test_kb_search_excludes_non_trade_lesson_via_source_type() -> None:
    """A non-trade_lesson source_type filter must scope retrieval to that type, not trade lessons."""
    ex = _executor()
    spy = AsyncMock(return_value=[])
    with patch.object(TradeLearningService, "get_relevant_lessons", spy):
        await ex._run_kb_search(uuid4(), {"source_type_filter": "research_note"}, {})
    _, kwargs = spy.call_args
    assert kwargs["source_type"] == "research_note"  # not silently forced to trade_lesson


@pytest.mark.anyio
async def test_kb_search_no_lessons_returns_safe_advisory() -> None:
    ex = _executor()
    config = {"source_type_filter": "trade_lesson"}
    context = {"input_payload": {"symbol": "ETHUSDT"}}
    with patch.object(TradeLearningService, "get_relevant_lessons", AsyncMock(return_value=[])):
        text, meta = await ex._run_kb_search(uuid4(), config, context)
    assert "no past trade_lesson entries" in text.lower()
    assert meta["matches"] == 0
    assert meta["advisory"] is True


@pytest.mark.anyio
async def test_kb_search_retrieval_error_degrades_to_empty_advisory() -> None:
    """A retrieval exception must NOT fail the step (no run failure) and NOT bypass any gate."""
    ex = _executor()
    config = {"source_type_filter": "trade_lesson"}
    context = {"input_payload": {"symbol": "BTCUSDT"}}
    boom = AsyncMock(side_effect=RuntimeError("db down"))
    with patch.object(TradeLearningService, "get_relevant_lessons", boom):
        text, meta = await ex._run_kb_search(uuid4(), config, context)
    assert meta["matches"] == 0  # safe empty, not a raised error
    assert meta["advisory"] is True
    assert "no past trade_lesson entries" in text.lower()


@pytest.mark.anyio
async def test_kb_search_without_filter_keeps_generic_path() -> None:
    """A step with no source_type_filter must NOT route through lesson retrieval."""
    ex = _executor()
    spy = AsyncMock(return_value=[])
    with (
        patch.object(TradeLearningService, "get_relevant_lessons", spy),
        patch("app.services.run_executor.DNAMemoryService") as dna,
    ):
        dna.return_value.get_relevant = AsyncMock(return_value=[])
        ex.db.execute = AsyncMock()  # generic fallback path touches knowledge_repo
        with patch(
            "app.services.run_executor.knowledge_repo.list_by_project",
            AsyncMock(return_value=([], 0)),
        ):
            _text, meta = await ex._run_kb_search(uuid4(), {"query": "anything"}, {})
    spy.assert_not_awaited()  # lesson retrieval was never used
    assert meta["runtime"] == "kb_search"
