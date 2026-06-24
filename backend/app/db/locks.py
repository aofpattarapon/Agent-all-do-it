"""Transaction-scoped Postgres advisory locks for serializing race-prone critical sections.

These complement the partial unique indexes added in the Phase 2A migration: the indexes are
the last-resort DB backstop, while an advisory lock held for the duration of a transaction
serializes the *check-then-act* windows (overlap guard, position-cap check, proposal execution)
so two concurrent workers cannot both pass a read-based gate before either writes.

``pg_advisory_xact_lock`` is automatically released when the transaction commits or rolls back,
so there is nothing to unlock manually. Locks are namespaced by an integer so unrelated callers
that hash to the same key in one namespace do not collide with another namespace.
"""

from __future__ import annotations

from enum import IntEnum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class LockNamespace(IntEnum):
    """Distinct integer namespaces so different lock domains never collide."""

    SCHEDULE_WORKFLOW = 1  # one scheduler tick at a time per workflow
    POSITION_CAP = 2  # one open-position cap check + open at a time per project
    PROPOSAL_EXECUTION = 3  # one execution at a time per proposal


def _key_from_uuid(value: UUID) -> int:
    """Derive a stable signed 32-bit key from a UUID for the two-int advisory-lock form."""
    # Postgres pg_advisory_xact_lock(int4, int4) expects 32-bit signed integers.
    return (value.int & 0x7FFFFFFF) - 0x40000000


async def advisory_xact_lock(db: AsyncSession, namespace: LockNamespace, value: UUID) -> None:
    """Acquire a transaction-scoped advisory lock for ``(namespace, value)``.

    Blocks until the lock is granted; released automatically at transaction end. On non-Postgres
    binds (e.g. unit tests with a mocked session) this is a harmless no-op statement.
    """
    if not _is_postgres(db):
        return
    await db.execute(select(func.pg_advisory_xact_lock(int(namespace), _key_from_uuid(value))))


def _is_postgres(db: AsyncSession) -> bool:
    """True only when the session is bound to a real Postgres engine."""
    try:
        return db.bind is not None and db.bind.dialect.name == "postgresql"
    except Exception:
        return False
