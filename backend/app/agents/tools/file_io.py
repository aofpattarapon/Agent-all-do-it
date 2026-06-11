"""Sandboxed file I/O tools for agents.

All operations are constrained to a per-project base directory:
``backend/data/agent_files/{project_id}/``. Paths are resolved and checked to
ensure they stay under that base — path traversal (``..``) is rejected.
"""

import logging
from pathlib import Path

from app.core.project_paths import project_agent_files_dir

logger = logging.getLogger(__name__)


class FileAccessError(Exception):
    """Raised when a requested path escapes the project sandbox."""


def _project_base(project_id: str) -> Path:
    """Return (and create) the sandbox base directory for a project."""
    return project_agent_files_dir(project_id).resolve()


def _resolve(project_id: str, path: str) -> Path:
    """Resolve ``path`` relative to the project sandbox, rejecting traversal."""
    base = _project_base(project_id)
    candidate = (base / path).resolve()
    if candidate != base and base not in candidate.parents:
        raise FileAccessError(f"Path {path!r} escapes the project sandbox")
    return candidate


def read_file(project_id: str, path: str) -> dict:
    """Read a UTF-8 text file from the project sandbox.

    Returns a dict with ``ok`` plus ``content`` on success or ``error`` on failure.
    """
    try:
        target = _resolve(project_id, path)
        content = target.read_text(encoding="utf-8")
    except FileAccessError as exc:
        return {"ok": False, "error": str(exc)}
    except FileNotFoundError:
        return {"ok": False, "error": f"File not found: {path}"}
    except Exception as exc:
        logger.warning("read_file failed: %s", exc)
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "content": content}


def write_file(project_id: str, path: str, content: str) -> dict:
    """Write a UTF-8 text file into the project sandbox.

    Parent directories are created as needed. Returns a dict with ``ok`` plus
    ``path``/``bytes_written`` on success or ``error`` on failure.
    """
    try:
        target = _resolve(project_id, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        written = target.write_text(content, encoding="utf-8")
    except FileAccessError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("write_file failed: %s", exc)
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "path": path, "bytes_written": written}


def list_dir(project_id: str, path: str = ".") -> dict:
    """List entries in a directory within the project sandbox.

    Returns a dict with ``ok`` plus ``entries`` (list of {name, is_dir}) on
    success or ``error`` on failure.
    """
    try:
        target = _resolve(project_id, path)
        if not target.exists():
            return {"ok": False, "error": f"Directory not found: {path}"}
        if not target.is_dir():
            return {"ok": False, "error": f"Not a directory: {path}"}
        entries = [
            {"name": child.name, "is_dir": child.is_dir()}
            for child in sorted(target.iterdir(), key=lambda p: p.name)
        ]
    except FileAccessError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("list_dir failed: %s", exc)
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "entries": entries}
