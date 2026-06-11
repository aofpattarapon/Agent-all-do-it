"""Automatic context compaction with DB + Obsidian persistence."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import context_compaction_repo
from app.services.model_fallback import run_with_fallback
from app.services.obsidian_exporter import export_compaction

if TYPE_CHECKING:
    from app.db.models.context_compaction import ContextCompaction
    from app.db.models.project import AgentConfig

logger = logging.getLogger(__name__)

COMPACTION_MARKER = "[COMPACTED CONTEXT]"
DEFAULT_KEEP_ITEMS = 10
MAX_FACTS = 8
MAX_ENTITIES = 8
MAX_RELATIONS = 8


@dataclass(slots=True)
class CompactionPayload:
    summary_text: str
    structured_facts: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    relations: list[dict[str, Any]]


@dataclass(slots=True)
class CompactionApplyResult:
    history: list[dict[str, str]]
    memory_block: str
    compaction_record: ContextCompaction | None
    compacted: bool


class ContextCompactionService:
    """Compacts oversized history segments and persists the result."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compact_conversation_history(
        self,
        *,
        history: list[dict[str, str]],
        keep_items: int | None = None,
        project_id: UUID | None = None,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
        thread_label: str | None = None,
    ) -> CompactionApplyResult:
        normalized = self._normalize_messages(history)
        if not normalized:
            return CompactionApplyResult([], "", None, False)

        keep = self._normalize_keep_items(keep_items)
        old_items, recent_items = self._split_items(normalized, keep)
        if not old_items:
            return CompactionApplyResult(normalized, "", None, False)

        record = await self._compact_items(
            items=old_items,
            source_type="conversation",
            trigger_reason="context_window_limit",
            project_id=project_id,
            agent_config_id=None,
            run_id=None,
            run_step_id=None,
            conversation_id=conversation_id,
            user_id=user_id,
            agent=None,
            metadata={
                "thread_label": thread_label or "default",
                "kept_raw_items": len(recent_items),
            },
        )
        memory_block = self._memory_block([record])
        compacted_history = []
        if memory_block:
            compacted_history.append({"role": "system", "content": memory_block})
        compacted_history.extend(recent_items)
        return CompactionApplyResult(
            history=compacted_history,
            memory_block=memory_block,
            compaction_record=record,
            compacted=True,
        )

    async def build_run_memory(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        run_step_id: UUID | None,
        agent: AgentConfig,
        items: list[dict[str, str]],
    ) -> tuple[str, ContextCompaction | None]:
        normalized = self._normalize_items(items)
        if not normalized:
            return "", None

        keep = self._normalize_keep_items(getattr(agent, "context_window_size", None))
        old_items, recent_items = self._split_items(normalized, keep)
        new_record = None
        if old_items and self._memory_enabled(agent):
            new_record = await self._compact_items(
                items=old_items,
                source_type="workflow_step",
                trigger_reason="context_window_limit",
                project_id=project_id,
                agent_config_id=getattr(agent, "id", None),
                run_id=run_id,
                run_step_id=run_step_id,
                conversation_id=None,
                user_id=None,
                agent=agent,
                metadata={
                    "kept_raw_items": len(recent_items),
                    "recent_step_keys": [item.get("label", "") for item in recent_items],
                },
            )

        records = await context_compaction_repo.list_recent(
            self.db,
            project_id=project_id,
            run_id=run_id,
            agent_config_id=getattr(agent, "id", None),
            limit=3,
        )
        memory_block = self._memory_block(records)
        if recent_items:
            recent_lines = ["## Recent raw context"]
            for item in recent_items:
                recent_lines.append(
                    f"- {item.get('label') or item.get('role') or 'context'}: "
                    f"{self._clip(item.get('content', ''), 220)}"
                )
            memory_block = "\n".join(
                [part for part in (memory_block, "\n".join(recent_lines)) if part]
            )
        return memory_block, new_record

    async def _compact_items(
        self,
        *,
        items: list[dict[str, str]],
        source_type: str,
        trigger_reason: str,
        project_id: UUID | None,
        agent_config_id: UUID | None,
        run_id: UUID | None,
        run_step_id: UUID | None,
        conversation_id: UUID | None,
        user_id: UUID | None,
        agent: AgentConfig | None,
        metadata: dict[str, Any],
    ) -> ContextCompaction:
        source_hash = self._source_hash(items, source_type=source_type)
        existing = await context_compaction_repo.get_by_source_hash(
            self.db,
            source_hash=source_hash,
            project_id=project_id,
            run_id=run_id,
            conversation_id=conversation_id,
        )
        if existing is not None:
            return existing

        payload = await self._summarize_items(items, agent=agent, source_type=source_type)
        source_char_count = sum(len(item.get("content", "")) for item in items)
        estimated_tokens_before = self.estimate_tokens_from_items(items)
        estimated_tokens_after = self.estimate_tokens(payload.summary_text)
        record = await context_compaction_repo.create(
            self.db,
            project_id=project_id,
            agent_config_id=agent_config_id,
            run_id=run_id,
            run_step_id=run_step_id,
            conversation_id=conversation_id,
            user_id=user_id,
            source_type=source_type,
            trigger_reason=trigger_reason,
            source_hash=source_hash,
            source_message_count=len(items),
            source_char_count=source_char_count,
            estimated_tokens_before=estimated_tokens_before,
            estimated_tokens_after=estimated_tokens_after,
            summary_text=payload.summary_text,
            structured_facts_json=payload.structured_facts,
            entities_json=payload.entities,
            relations_json=payload.relations,
            metadata_json=metadata,
        )
        export_compaction(
            project_id=project_id,
            record_id=record.id,
            source_type=source_type,
            run_id=run_id,
            run_step_id=run_step_id,
            conversation_id=conversation_id,
            user_id=user_id,
            summary_text=payload.summary_text,
            structured_facts=payload.structured_facts,
            entities=payload.entities,
            relations=payload.relations,
            metadata=metadata,
            estimated_tokens_before=estimated_tokens_before,
            estimated_tokens_after=estimated_tokens_after,
        )
        return record

    async def _summarize_items(
        self,
        items: list[dict[str, str]],
        *,
        agent: AgentConfig | None,
        source_type: str,
    ) -> CompactionPayload:
        if agent is not None:
            payload = await self._summarize_with_llm(items, agent=agent, source_type=source_type)
            if payload is not None:
                return payload
        return self._heuristic_summary(items, source_type=source_type)

    async def _summarize_with_llm(
        self,
        items: list[dict[str, str]],
        *,
        agent: AgentConfig,
        source_type: str,
    ) -> CompactionPayload | None:
        source_text = self._serialize_items(items)
        prompt = (
            "Compact the following historical context into strict JSON.\n"
            "Return ONLY JSON with keys summary, facts, entities, relations.\n"
            "facts must be a list of objects with keys topic and detail.\n"
            "entities must be a list of objects with keys name and type.\n"
            "relations must be a list of objects with keys from, to, relation.\n"
            "Keep the summary concise but preserve decisions, constraints, outcomes, and unresolved items.\n\n"
            f"source_type: {source_type}\n"
            f"context:\n{source_text}"
        )
        system_prompt = (
            "You are a context compaction engine. Preserve decision-critical information, "
            "drop repetition, and return JSON only."
        )
        try:
            output, _meta = await run_with_fallback(
                agent,
                prompt=prompt,
                system_prompt=system_prompt,
            )
            data = self._parse_json_output(output)
            if not data:
                return None
            summary = str(data.get("summary") or "").strip()
            if not summary:
                return None
            return CompactionPayload(
                summary_text=summary,
                structured_facts=self._coerce_list_of_dicts(data.get("facts")),
                entities=self._coerce_list_of_dicts(data.get("entities")),
                relations=self._coerce_list_of_dicts(data.get("relations")),
            )
        except Exception as exc:
            logger.debug("LLM compaction fallback engaged: %s", exc)
            return None

    @staticmethod
    def _heuristic_summary(
        items: list[dict[str, str]],
        *,
        source_type: str,
    ) -> CompactionPayload:
        bullets = []
        facts = []
        entities = []
        relations = []
        last_label = None
        for idx, item in enumerate(items[:MAX_FACTS]):
            label = item.get("label") or item.get("role") or f"item_{idx + 1}"
            content = item.get("content", "").strip()
            if not content:
                continue
            excerpt = ContextCompactionService._clip(content, 220)
            bullets.append(f"- {label}: {excerpt}")
            facts.append({"topic": label, "detail": excerpt})
            entities.append({"name": label, "type": item.get("role") or source_type})
            if last_label is not None and len(relations) < MAX_RELATIONS:
                relations.append({"from": last_label, "to": label, "relation": "precedes"})
            last_label = label
        if not bullets:
            bullets = ["- Historical context compacted."]
        return CompactionPayload(
            summary_text="\n".join(bullets[:MAX_FACTS]),
            structured_facts=facts[:MAX_FACTS],
            entities=entities[:MAX_ENTITIES],
            relations=relations[:MAX_RELATIONS],
        )

    @staticmethod
    def _parse_json_output(output: str) -> dict[str, Any] | None:
        text = (output or "").strip()
        if not text:
            return None
        candidates = [text]
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1])
        for candidate in candidates:
            try:
                data = json.loads(candidate)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                continue
        return None

    @staticmethod
    def _coerce_list_of_dicts(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        out: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                out.append(item)
        return out

    @staticmethod
    def _normalize_messages(history: list[dict[str, str]]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for msg in history:
            role = str(msg.get("role") or "").strip()
            content = str(msg.get("content") or "").strip()
            if not role or not content:
                continue
            out.append({"role": role, "content": content})
        return out

    @staticmethod
    def _normalize_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for item in items:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            out.append(
                {
                    "role": str(item.get("role") or "").strip(),
                    "label": str(item.get("label") or "").strip(),
                    "content": content,
                }
            )
        return out

    @staticmethod
    def _split_items(
        items: list[dict[str, str]], keep_items: int
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        if len(items) <= keep_items:
            return [], items
        return items[:-keep_items], items[-keep_items:]

    @staticmethod
    def _normalize_keep_items(value: int | None) -> int:
        if not isinstance(value, int) or value <= 0:
            return DEFAULT_KEEP_ITEMS
        return max(2, min(value, 100))

    @staticmethod
    def _memory_enabled(agent: AgentConfig) -> bool:
        # Compaction is enabled globally so existing and newly created agents
        # benefit immediately. ``memory_type`` can still be used later to
        # control reuse policies, but it should not disable basic compaction.
        _ = agent
        return True

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return max(1, (len(text or "") + 3) // 4)

    def estimate_tokens_from_items(self, items: list[dict[str, str]]) -> int:
        return self.estimate_tokens(self._serialize_items(items))

    @staticmethod
    def _serialize_items(items: list[dict[str, str]]) -> str:
        lines = []
        for idx, item in enumerate(items, start=1):
            label = item.get("label") or item.get("role") or f"item_{idx}"
            lines.append(f"[{idx}] {label}\n{item.get('content', '')}")
        return "\n\n".join(lines)

    def _source_hash(self, items: list[dict[str, str]], *, source_type: str) -> str:
        normalized = json.dumps(
            {
                "source_type": source_type,
                "items": [
                    {
                        "role": item.get("role", ""),
                        "label": item.get("label", ""),
                        "content": item.get("content", ""),
                    }
                    for item in items
                ],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _clip(value: str, limit: int) -> str:
        text = value.strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _memory_block(records: list[ContextCompaction]) -> str:
        if not records:
            return ""
        lines = [COMPACTION_MARKER, "Use this as compacted historical context."]
        for idx, record in enumerate(reversed(records), start=1):
            lines.append(f"## Memory {idx}")
            lines.append(record.summary_text.strip() or "- No summary available.")
        return "\n".join(lines).strip()
