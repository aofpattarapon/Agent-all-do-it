from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.context_compaction import (
    COMPACTION_MARKER,
    ContextCompactionService,
)


def _record(summary: str = "- summary"):
    return SimpleNamespace(
        id=uuid4(),
        summary_text=summary,
        created_at=None,
    )


@pytest.mark.anyio
async def test_compact_conversation_history_replaces_old_messages_with_summary():
    db = AsyncMock()
    service = ContextCompactionService(db)
    history = [
        {"role": "user", "content": f"user {idx}"}
        if idx % 2 == 0
        else {"role": "assistant", "content": f"assistant {idx}"}
        for idx in range(12)
    ]

    with (
        patch(
            "app.services.context_compaction.context_compaction_repo.get_by_source_hash",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.context_compaction.context_compaction_repo.create",
            new=AsyncMock(return_value=_record("- compacted conversation")),
        ) as create_mock,
        patch(
            "app.services.context_compaction.export_compaction",
            return_value=None,
        ),
    ):
        result = await service.compact_conversation_history(history=history, keep_items=4)

    assert result.compacted is True
    assert result.history[0]["role"] == "system"
    assert COMPACTION_MARKER in result.history[0]["content"]
    assert len(result.history) == 5
    create_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_compact_conversation_history_reuses_existing_record():
    db = AsyncMock()
    service = ContextCompactionService(db)
    existing = _record("- existing summary")
    history = [{"role": "user", "content": f"message {idx}"} for idx in range(11)]

    with (
        patch(
            "app.services.context_compaction.context_compaction_repo.get_by_source_hash",
            new=AsyncMock(return_value=existing),
        ),
        patch(
            "app.services.context_compaction.context_compaction_repo.create",
            new=AsyncMock(),
        ) as create_mock,
    ):
        result = await service.compact_conversation_history(history=history, keep_items=3)

    assert result.compaction_record is existing
    assert "- existing summary" in result.memory_block
    create_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_build_run_memory_includes_summary_and_recent_raw_context():
    db = AsyncMock()
    service = ContextCompactionService(db)
    agent = SimpleNamespace(
        id=uuid4(),
        memory_type="none",
        context_window_size=2,
    )
    items = [
        {"role": "workflow_step", "label": "step_a", "content": "First output"},
        {"role": "workflow_step", "label": "step_b", "content": "Second output"},
        {"role": "workflow_step", "label": "step_c", "content": "Third output"},
        {"role": "workflow_step", "label": "step_d", "content": "Fourth output"},
    ]
    created = _record("- prior steps compacted")

    with (
        patch.object(
            service,
            "_compact_items",
            new=AsyncMock(return_value=created),
        ) as compact_mock,
        patch(
            "app.services.context_compaction.context_compaction_repo.list_recent",
            new=AsyncMock(return_value=[created]),
        ),
    ):
        memory_block, record = await service.build_run_memory(
            project_id=uuid4(),
            run_id=uuid4(),
            run_step_id=uuid4(),
            agent=agent,
            items=items,
        )

    assert record is created
    assert COMPACTION_MARKER in memory_block
    assert "Recent raw context" in memory_block
    assert "step_c" in memory_block
    assert "step_d" in memory_block
    compact_mock.assert_awaited_once()
