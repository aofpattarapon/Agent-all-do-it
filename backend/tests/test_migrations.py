"""Migration tests — verify the Alembic upgrade/downgrade cycle against an ISOLATED database.

These tests shell out to `alembic` and would otherwise migrate whatever
``settings.DATABASE_URL_SYNC`` points at — i.e. the developer/production database. To make that
impossible they are **isolated-DB-gated**: they only run when ``MIGRATION_TEST_DATABASE_URL`` is
set to a throwaway database, and they hard-skip if that URL resolves to the normal app DB. The
URL is injected into the subprocess so Alembic's ``env.py`` (`get_url`) uses it instead of the
dev DB.

By default (no env var) the whole module is skipped, so `uv run pytest` can never silently
migrate the dev database. The full base→head upgrade/downgrade round-trip is also covered, with
self-managed scratch-DB creation, by `tests/db/test_migration_indexes_idempotency.py`.

To run locally against a throwaway DB:
    createdb pda_migtest
    MIGRATION_TEST_DATABASE_URL=postgresql://postgres:@localhost:5433/pda_migtest \
        uv run pytest tests/test_migrations.py
"""

import os
import subprocess
import sys

import pytest

from app.core.config import settings

# Explicit opt-in: an isolated, throwaway database URL. Unset → the whole module is skipped.
_MIGRATION_DB_URL = os.getenv("MIGRATION_TEST_DATABASE_URL", "").strip()
# Destructive (data-wiping) variants additionally require CI=true.
_IN_CI = os.getenv("CI", "").lower() in ("1", "true", "yes")


def _points_at_dev_db() -> bool:
    """True if the configured test URL resolves to the same database as the normal app DB."""
    return bool(_MIGRATION_DB_URL) and _MIGRATION_DB_URL == settings.DATABASE_URL_SYNC


# Skip unless an isolated DB URL is provided; refuse outright if it aliases the dev DB.
_requires_isolated_db = pytest.mark.skipif(
    not _MIGRATION_DB_URL,
    reason="Set MIGRATION_TEST_DATABASE_URL to a throwaway DB to run migration subprocess tests",
)


def _alembic_env() -> dict[str, str]:
    """Subprocess env that forces Alembic (env.py get_url) to use the isolated test DB."""
    env = os.environ.copy()
    env["MIGRATION_TEST_DATABASE_URL"] = _MIGRATION_DB_URL
    return env


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        cwd=".",
        env=_alembic_env(),
    )


@_requires_isolated_db
class TestMigrations:
    """Test Alembic migration integrity against an isolated database only."""

    @pytest.fixture(autouse=True)
    def _guard_not_dev_db(self) -> None:
        # Hard stop: never run these against the developer/production database.
        if _points_at_dev_db():
            pytest.skip(
                "MIGRATION_TEST_DATABASE_URL must point at a throwaway DB, not the app DB "
                "(it equals settings.DATABASE_URL_SYNC) — refusing to migrate the dev DB."
            )

    def test_upgrade_head(self):
        """Test that all migrations can be applied successfully."""
        result = _run_alembic("upgrade", "head")
        assert result.returncode == 0, f"Migration upgrade failed:\n{result.stderr}"

    @pytest.mark.skipif(
        not _IN_CI, reason="Destructive: wipes all data — only runs in CI (set CI=true)"
    )
    def test_downgrade_base(self):
        """Test that all migrations can be rolled back."""
        up = _run_alembic("upgrade", "head")
        assert up.returncode == 0, f"Migration upgrade failed:\n{up.stderr}"

        down = _run_alembic("downgrade", "base")
        assert down.returncode == 0, f"Migration downgrade failed:\n{down.stderr}"

    @pytest.mark.skipif(
        not _IN_CI, reason="Destructive: wipes all data — only runs in CI (set CI=true)"
    )
    def test_upgrade_downgrade_cycle(self):
        """Test that upgrade → downgrade → upgrade produces consistent state."""
        for cmd in ["upgrade head", "downgrade base", "upgrade head"]:
            action, target = cmd.split()
            result = _run_alembic(action, target)
            assert result.returncode == 0, f"alembic {cmd} failed:\n{result.stderr}"

    def test_current_matches_head(self):
        """Test that current migration revision matches head after upgrade."""
        up = _run_alembic("upgrade", "head")
        assert up.returncode == 0, f"Migration upgrade failed:\n{up.stderr}"

        heads = _run_alembic("heads")
        assert heads.returncode == 0

        if not heads.stdout.strip():
            pytest.skip("No migration revisions found — nothing to verify")

        result = _run_alembic("current")
        assert result.returncode == 0
        assert "(head)" in result.stdout, (
            f"Current revision is not at head:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
