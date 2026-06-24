"""DB-backed checks for project isolation hardening."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.project_paths import project_compactions_dir, project_uploads_dir
from app.db.models.chat_file import ChatFile
from app.db.models.context_compaction import ContextCompaction
from app.db.models.conversation import Conversation
from app.db.models.project import Project
from app.db.models.user import User
from app.db.session import get_worker_db_context
from app.repositories import chat_file as chat_file_repo
from app.repositories import context_compaction as context_compaction_repo
from app.repositories import conversation as conversation_repo
from app.services.file_storage import LocalFileStorage


@pytest.fixture
async def db_session() -> AsyncSession:
    """Open a normal app DB session for integration tests."""
    async with get_worker_db_context() as session:
        yield session


async def _seed_user_and_projects(db: AsyncSession) -> tuple[User, Project, Project]:
    user = User(
        email=f"isolation-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="user",
        is_active=True,
        is_app_admin=False,
    )
    db.add(user)
    await db.flush()

    project_a = Project(user_id=user.id, name=f"Project A {uuid4().hex[:6]}")
    project_b = Project(user_id=user.id, name=f"Project B {uuid4().hex[:6]}")
    db.add_all([project_a, project_b])
    await db.flush()
    return user, project_a, project_b


async def _cleanup_user_scope(db: AsyncSession, user_id) -> None:
    await db.execute(delete(ChatFile).where(ChatFile.user_id == user_id))
    await db.execute(delete(ContextCompaction).where(ContextCompaction.user_id == user_id))
    await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
    await db.execute(delete(Project).where(Project.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.flush()


@pytest.mark.anyio
async def test_project_conversations_are_filtered_by_project(db_session: AsyncSession) -> None:
    user, project_a, project_b = await _seed_user_and_projects(db_session)
    try:
        conv_a = await conversation_repo.create_conversation(
            db_session,
            user_id=user.id,
            project_id=project_a.id,
            title="Project A chat",
        )
        conv_b = await conversation_repo.create_conversation(
            db_session,
            user_id=user.id,
            project_id=project_b.id,
            title="Project B chat",
        )

        items_a = await conversation_repo.get_conversations_by_user(
            db_session,
            user_id=user.id,
            project_id=project_a.id,
            include_archived=True,
        )
        items_b = await conversation_repo.get_conversations_by_user(
            db_session,
            user_id=user.id,
            project_id=project_b.id,
            include_archived=True,
        )

        assert [item.id for item in items_a] == [conv_a.id]
        assert [item.id for item in items_b] == [conv_b.id]
    finally:
        await _cleanup_user_scope(db_session, user.id)


@pytest.mark.anyio
async def test_project_uploads_resolve_under_project_root_and_keep_scope(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    user, project_a, project_b = await _seed_user_and_projects(db_session)
    try:
        storage = LocalFileStorage(base_dir=tmp_path / "media")

        path_a = await storage.save(
            str(user.id), "report.txt", b"alpha", project_id=str(project_a.id)
        )
        path_b = await storage.save(
            str(user.id), "report.txt", b"beta", project_id=str(project_b.id)
        )

        record_a = await chat_file_repo.create(
            db_session,
            user_id=user.id,
            project_id=project_a.id,
            filename="report.txt",
            mime_type="text/plain",
            size=5,
            storage_path=path_a,
            file_type="text",
            parsed_content="alpha",
        )
        record_b = await chat_file_repo.create(
            db_session,
            user_id=user.id,
            project_id=project_b.id,
            filename="report.txt",
            mime_type="text/plain",
            size=4,
            storage_path=path_b,
            file_type="text",
            parsed_content="beta",
        )

        assert record_a.project_id == project_a.id
        assert record_b.project_id == project_b.id
        assert str(project_uploads_dir(project_a.id, user.id)) in path_a
        assert str(project_uploads_dir(project_b.id, user.id)) in path_b
        assert path_a != path_b
    finally:
        await _cleanup_user_scope(db_session, user.id)


@pytest.mark.anyio
async def test_project_compactions_do_not_cross_project_queries(
    db_session: AsyncSession,
) -> None:
    user, project_a, project_b = await _seed_user_and_projects(db_session)
    try:
        record_a = await context_compaction_repo.create(
            db_session,
            project_id=project_a.id,
            agent_config_id=None,
            run_id=None,
            run_step_id=None,
            conversation_id=None,
            user_id=user.id,
            source_type="conversation",
            trigger_reason="context_window_limit",
            source_hash="hash-shared",
            source_message_count=2,
            source_char_count=20,
            estimated_tokens_before=10,
            estimated_tokens_after=5,
            summary_text="A summary",
            structured_facts_json=[],
            entities_json=[],
            relations_json=[],
            metadata_json={"scope": "a"},
        )
        record_b = await context_compaction_repo.create(
            db_session,
            project_id=project_b.id,
            agent_config_id=None,
            run_id=None,
            run_step_id=None,
            conversation_id=None,
            user_id=user.id,
            source_type="conversation",
            trigger_reason="context_window_limit",
            source_hash="hash-shared",
            source_message_count=2,
            source_char_count=20,
            estimated_tokens_before=10,
            estimated_tokens_after=5,
            summary_text="B summary",
            structured_facts_json=[],
            entities_json=[],
            relations_json=[],
            metadata_json={"scope": "b"},
        )

        recent_a = await context_compaction_repo.list_recent(
            db_session,
            project_id=project_a.id,
            user_id=user.id,
            limit=10,
        )
        recent_b = await context_compaction_repo.list_recent(
            db_session,
            project_id=project_b.id,
            user_id=user.id,
            limit=10,
        )
        by_hash_a = await context_compaction_repo.get_by_source_hash(
            db_session,
            source_hash="hash-shared",
            project_id=project_a.id,
        )
        by_hash_b = await context_compaction_repo.get_by_source_hash(
            db_session,
            source_hash="hash-shared",
            project_id=project_b.id,
        )

        assert [item.id for item in recent_a] == [record_a.id]
        assert [item.id for item in recent_b] == [record_b.id]
        assert by_hash_a is not None and by_hash_a.id == record_a.id
        assert by_hash_b is not None and by_hash_b.id == record_b.id
    finally:
        await _cleanup_user_scope(db_session, user.id)


@pytest.mark.anyio
async def test_project_compaction_paths_are_project_specific() -> None:
    project_a_id = uuid4()
    project_b_id = uuid4()
    assert project_compactions_dir(project_a_id) != project_compactions_dir(project_b_id)
    assert str(project_a_id) in str(project_compactions_dir(project_a_id))
    assert str(project_b_id) in str(project_compactions_dir(project_b_id))
