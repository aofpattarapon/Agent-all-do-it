"""File storage service for chat file uploads."""

import logging
import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings
from app.core.project_paths import (
    GLOBAL_ROOT,
    PROJECTS_ROOT,
    personal_uploads_dir,
    project_uploads_dir,
)

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "text/css",
    "text/xml",
    "text/x-python",
    "text/javascript",
    "text/x-yaml",
    "application/json",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/x-yaml",
}

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


def classify_file(mime_type: str, filename: str) -> str:
    """Classify file type based on MIME type and extension."""
    if mime_type in IMAGE_MIME_TYPES:
        return "image"
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return "pdf"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "docx" or "wordprocessingml" in mime_type:
        return "docx"
    return "text"


_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w.\-]+")


def _sanitize_filename(filename: str) -> str:
    """Strip path separators, NULL bytes, and unsafe chars from a filename.

    The result is always a single path component with no traversal segments.
    Empty results fall back to ``"file"`` to preserve a non-empty name.
    """
    base = Path(filename).name.replace("\x00", "")
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", base).strip("._")
    return cleaned or "file"


def make_storage_filename(filename: str) -> str:
    """Create a unique storage filename to prevent collisions and path traversal."""
    safe = _sanitize_filename(filename)
    return f"{uuid.uuid4().hex[:12]}_{safe}"


class BaseFileStorage(ABC):
    """Abstract file storage backend."""

    @abstractmethod
    async def save(
        self,
        user_id: str,
        filename: str,
        data: bytes,
        *,
        project_id: str | None = None,
    ) -> str:
        """Save file and return storage path/key."""

    @abstractmethod
    async def load(self, storage_path: str) -> bytes:
        """Load file bytes by storage path."""

    @abstractmethod
    async def delete(self, storage_path: str) -> None:
        """Delete file by storage path."""

    def get_full_path(self, storage_path: str) -> Path | None:
        """Return absolute filesystem path if available (local storage only)."""
        return None  # pragma: no cover


class LocalFileStorage(BaseFileStorage):
    """Store files on local filesystem."""

    def __init__(self, base_dir: str | Path = "media"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_path: str) -> Path:
        """Resolve a storage path under base_dir, rejecting traversal attempts."""
        candidate = Path(storage_path)
        if not candidate.is_absolute():
            candidate = (self.base_dir / candidate).resolve()
        candidate = candidate.resolve()
        roots = [self.base_dir.resolve()]
        for root in (PROJECTS_ROOT.resolve(), GLOBAL_ROOT.resolve()):
            if root.exists():
                roots.append(root)
        if not any(candidate == root or root in candidate.parents for root in roots):
            raise ValueError(f"Path escapes storage roots: {storage_path}")
        return candidate

    async def save(
        self,
        user_id: str,
        filename: str,
        data: bytes,
        *,
        project_id: str | None = None,
    ) -> str:
        safe_user = _sanitize_filename(user_id)
        if project_id:
            user_dir = project_uploads_dir(project_id, safe_user)
        else:
            user_dir = personal_uploads_dir(safe_user)
        user_dir.mkdir(parents=True, exist_ok=True)
        storage_name = make_storage_filename(filename)
        file_path = user_dir / storage_name
        file_path.write_bytes(data)
        return str(file_path.resolve())

    async def load(self, storage_path: str) -> bytes:
        file_path = self._resolve_safe_path(storage_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {storage_path}")
        return file_path.read_bytes()

    async def delete(self, storage_path: str) -> None:
        file_path = self._resolve_safe_path(storage_path)
        if file_path.exists():
            file_path.unlink()

    def get_full_path(self, storage_path: str) -> Path | None:
        """Return absolute filesystem path for local files."""
        try:
            file_path = self._resolve_safe_path(storage_path)
        except ValueError:
            return None
        return file_path if file_path.exists() else None


def get_file_storage() -> BaseFileStorage:
    """Factory: create file storage backend based on settings."""
    media_dir = getattr(settings, "MEDIA_DIR", "media")
    return LocalFileStorage(base_dir=media_dir)
