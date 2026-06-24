"""Obsidian Vault Exporter — writes agent step outputs as Markdown notes.

Each run step is written to:
  data/vaults/{project_id}/{agent_name}/YYYY-MM-DD/{run_id}_{step_index}.md

Writes are atomic: data is written to a .tmp file and then renamed,
so a crash mid-write never leaves a corrupted note.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.core.project_paths import (
    global_compactions_dir,
    project_compactions_dir,
    project_vault_dir,
)

logger = logging.getLogger(__name__)


def export_step(
    *,
    project_id: UUID,
    run_id: UUID,
    step_index: int,
    agent_name: str,
    step_kind: str,
    output_text: str,
    tokens_used: int | None = None,
) -> Path | None:
    """Write a step's output as a Markdown note in the project's Obsidian vault.

    Returns the path of the written file, or None if writing failed.
    """
    try:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        safe_name = _safe(agent_name) or "agent"
        note_dir = project_vault_dir(project_id) / safe_name / today
        note_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{run_id}_{step_index:02d}.md"
        note_path = note_dir / filename
        tmp_path = note_path.with_suffix(".tmp")

        frontmatter = _frontmatter(
            project_id=project_id,
            run_id=run_id,
            step_index=step_index,
            agent_name=agent_name,
            step_kind=step_kind,
            tokens_used=tokens_used,
        )
        content = f"{frontmatter}\n\n{output_text}"

        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.rename(note_path)
        logger.debug("Obsidian note written: %s", note_path)
        return note_path
    except Exception as exc:
        logger.warning("ObsidianExporter.export_step failed: %s", exc)
        return None


def export_compaction(
    *,
    project_id: UUID | None,
    record_id: UUID,
    source_type: str,
    run_id: UUID | None,
    run_step_id: UUID | None,
    conversation_id: UUID | None,
    user_id: UUID | None,
    summary_text: str,
    structured_facts: list[dict],
    entities: list[dict],
    relations: list[dict],
    metadata: dict,
    estimated_tokens_before: int,
    estimated_tokens_after: int,
) -> Path | None:
    """Write a compaction record as a Markdown note in the vault."""
    try:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        scope = _safe(source_type) or "memory"
        base = (
            project_compactions_dir(project_id)
            if project_id is not None
            else global_compactions_dir()
        )
        note_dir = base / scope / today
        note_dir.mkdir(parents=True, exist_ok=True)

        note_path = note_dir / f"{record_id}.md"
        tmp_path = note_path.with_suffix(".tmp")
        content = _compaction_content(
            project_id=project_id,
            record_id=record_id,
            source_type=source_type,
            run_id=run_id,
            run_step_id=run_step_id,
            conversation_id=conversation_id,
            user_id=user_id,
            summary_text=summary_text,
            structured_facts=structured_facts,
            entities=entities,
            relations=relations,
            metadata=metadata,
            estimated_tokens_before=estimated_tokens_before,
            estimated_tokens_after=estimated_tokens_after,
        )
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.rename(note_path)
        logger.debug("Obsidian compaction note written: %s", note_path)
        return note_path
    except Exception as exc:
        logger.warning("ObsidianExporter.export_compaction failed: %s", exc)
        return None


def _frontmatter(
    *,
    project_id: UUID,
    run_id: UUID,
    step_index: int,
    agent_name: str,
    step_kind: str,
    tokens_used: int | None,
) -> str:
    now = datetime.now(UTC).isoformat()
    tokens_line = f"tokens_used: {tokens_used}" if tokens_used is not None else "tokens_used: null"
    return (
        "---\n"
        f"project_id: {project_id}\n"
        f"run_id: {run_id}\n"
        f"step_index: {step_index}\n"
        f"agent: {agent_name}\n"
        f"step_kind: {step_kind}\n"
        f"timestamp: {now}\n"
        f"{tokens_line}\n"
        "---"
    )


def _safe(name: str) -> str:
    """Strip characters unsafe for directory names."""
    return "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()


def _compaction_content(
    *,
    project_id: UUID | None,
    record_id: UUID,
    source_type: str,
    run_id: UUID | None,
    run_step_id: UUID | None,
    conversation_id: UUID | None,
    user_id: UUID | None,
    summary_text: str,
    structured_facts: list[dict],
    entities: list[dict],
    relations: list[dict],
    metadata: dict,
    estimated_tokens_before: int,
    estimated_tokens_after: int,
) -> str:
    now = datetime.now(UTC).isoformat()
    frontmatter_lines = [
        "---",
        f"record_id: {record_id}",
        f"project_id: {project_id if project_id is not None else 'null'}",
        f"source_type: {source_type}",
        f"run_id: {run_id if run_id is not None else 'null'}",
        f"run_step_id: {run_step_id if run_step_id is not None else 'null'}",
        f"conversation_id: {conversation_id if conversation_id is not None else 'null'}",
        f"user_id: {user_id if user_id is not None else 'null'}",
        f"estimated_tokens_before: {estimated_tokens_before}",
        f"estimated_tokens_after: {estimated_tokens_after}",
        f"timestamp: {now}",
        "---",
        "",
        "# Summary",
        summary_text.strip() or "- No summary available.",
        "",
        "# Facts",
    ]
    if structured_facts:
        frontmatter_lines.extend(f"- {fact}" for fact in structured_facts)
    else:
        frontmatter_lines.append("- None")
    frontmatter_lines.extend(["", "# Entities"])
    if entities:
        frontmatter_lines.extend(f"- {entity}" for entity in entities)
    else:
        frontmatter_lines.append("- None")
    frontmatter_lines.extend(["", "# Relations"])
    if relations:
        frontmatter_lines.extend(f"- {relation}" for relation in relations)
    else:
        frontmatter_lines.append("- None")
    frontmatter_lines.extend(
        ["", "# Metadata", f"```json\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n```"]
    )
    return "\n".join(frontmatter_lines)
