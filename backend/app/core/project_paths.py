"""Canonical filesystem paths for project-scoped artifacts."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = _BACKEND_ROOT / "data"
PROJECTS_ROOT = DATA_ROOT / "projects"
GLOBAL_ROOT = DATA_ROOT / "_global"


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_root(project_id: str | UUID) -> Path:
    return _ensure(PROJECTS_ROOT / str(project_id))


def project_vault_dir(project_id: str | UUID) -> Path:
    return _ensure(project_root(project_id) / "vault")


def project_agent_files_dir(project_id: str | UUID) -> Path:
    return _ensure(project_root(project_id) / "agent_files")


def project_uploads_dir(project_id: str | UUID, user_id: str | UUID | None = None) -> Path:
    base = project_root(project_id) / "uploads"
    if user_id is not None:
        base = base / str(user_id)
    return _ensure(base)


def project_reports_dir(project_id: str | UUID) -> Path:
    return _ensure(project_root(project_id) / "reports")


def project_exports_dir(project_id: str | UUID) -> Path:
    return _ensure(project_root(project_id) / "exports")


def project_run_artifacts_dir(project_id: str | UUID) -> Path:
    return _ensure(project_root(project_id) / "run_artifacts")


def project_compactions_dir(project_id: str | UUID) -> Path:
    return _ensure(project_root(project_id) / "compactions")


def global_compactions_dir() -> Path:
    return _ensure(GLOBAL_ROOT / "compactions")


def personal_uploads_dir(user_id: str | UUID) -> Path:
    return _ensure(GLOBAL_ROOT / "uploads" / str(user_id))
