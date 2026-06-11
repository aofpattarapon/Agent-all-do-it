"""Direct agent chat service — runs a single agent with its knowledge context."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories import agent_config_repo, knowledge_repo
from app.schemas.agent_chat import AgentChatResponse
from app.services.model_fallback import run_with_fallback


class AgentChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def chat(
        self,
        agent_config_id: UUID,
        project_id: UUID,
        message: str,
        include_knowledge: bool = True,
    ) -> AgentChatResponse:
        agent = await agent_config_repo.get_by_id(self.db, agent_config_id)
        if not agent or agent.project_id != project_id:
            raise NotFoundError(message="Agent not found", details={"agent_id": str(agent_config_id)})

        # Build system prompt from agent config + knowledge
        system_parts = [agent.system_prompt or f"You are {agent.name}, a {agent.role}."]

        if include_knowledge:
            # Get agent-specific docs first, then project-level docs
            agent_docs, _ = await knowledge_repo.list_by_agent(
                self.db, agent_config_id=agent_config_id, project_id=project_id, limit=10
            )
            project_docs, _ = await knowledge_repo.list_by_project(
                self.db, project_id=project_id, limit=5
            )
            # Project docs that aren't agent-specific
            shared_docs = [d for d in project_docs if d.agent_config_id is None]
            all_docs = agent_docs + shared_docs[:3]

            if all_docs:
                system_parts.append("\n\n## Knowledge Base\n")
                for doc in all_docs[:8]:
                    system_parts.append(f"### {doc.title}\n{doc.content[:800]}\n")

        system_prompt = "\n".join(system_parts)

        # Dispatch to the runtime adapter selected by agent.runtime_kind, with fallback.
        try:
            response_text, metadata = await run_with_fallback(
                agent,
                prompt=message,
                system_prompt=system_prompt,
                db=self.db,
            )
            tokens = metadata.get("tokens_used")
        except Exception as exc:
            response_text, tokens = f"[Agent error: {exc}]", None

        return AgentChatResponse(
            response=response_text,
            agent_name=agent.name,
            agent_role=agent.role,
            tokens_used=tokens,
        )
