"""LangGraph Supervisor v2 — central hub that orchestrates project agents.

Pipeline data flow (v2):
  Each agent receives the PREVIOUS agent's structured output, not just the
  original task. This creates a proper data pipeline where Monitor feeds
  Analyst, Analyst feeds Trader, etc. — rather than all agents independently
  re-deriving from the same raw task.

Each project has a list of AgentConfigs. The supervisor:
1. Receives a task
2. Routes to sub-agents sequentially via the agent queue
3. Each sub-agent receives (original_task + previous_output) as structured input
4. Aggregates all results into a final response
"""

import logging
import operator
from typing import Annotated, Any
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)


class SupervisorState(TypedDict):
    task: str
    project_id: str
    step_index: int  # which step in the pipeline we're on
    agent_queue: list[dict]
    current_agent: dict | None  # the agent currently being processed
    pending_handoff_id: str | None
    last_output: str  # output from the previous agent step
    agent_results: Annotated[dict[str, str], lambda a, b: {**a, **b}]
    messages: Annotated[list[BaseMessage], operator.add]
    final_response: str | None


class SupervisorAgent:
    """Orchestrates multiple agents defined in a project's AgentConfig list."""

    def __init__(self, agent_configs: list[dict], run_id: str = "") -> None:
        self.agent_configs = [cfg for cfg in agent_configs if cfg.get("is_active", True)]
        self.run_id = run_id
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        workflow = StateGraph(SupervisorState)
        workflow.add_node("dispatch", self._dispatch_node)
        workflow.add_node("run_agent", self._run_agent_node)
        workflow.add_node("aggregate", self._aggregate_node)

        workflow.set_entry_point("dispatch")
        workflow.add_conditional_edges(
            "dispatch",
            self._route_after_dispatch,
            {"run_agent": "run_agent", "aggregate": "aggregate", "__end__": END},
        )
        workflow.add_edge("run_agent", "dispatch")
        workflow.add_edge("aggregate", END)
        return workflow.compile()

    async def _mark_handoff_received(self, handoff_id: str) -> None:
        from app.db.session import get_db_context
        from app.repositories import handoff_repo

        try:
            async with get_db_context() as db:
                db_handoff = await handoff_repo.get_by_id(db, UUID(handoff_id))
                if db_handoff and db_handoff.status == "sent":
                    await handoff_repo.update(
                        db,
                        db_handoff=db_handoff,
                        update_data={"status": "received"},
                    )
                    await db.commit()
        except Exception as exc:
            logger.debug("Failed to mark handoff %s received: %s", handoff_id, exc)

    async def _create_handoff(
        self,
        *,
        state: SupervisorState,
        agent_cfg: dict,
        next_agent: dict,
        output_text: str,
    ) -> str | None:
        from app.db.session import get_db_context
        from app.repositories import handoff_repo

        summary = (
            f"{agent_cfg['name']} completed and handed work to {next_agent['name']}: "
            f"{output_text[:240].strip()}"
        ).strip()
        package_json = {
            "original_task": state["task"],
            "from_agent_name": agent_cfg["name"],
            "to_agent_name": next_agent["name"],
            "upstream_output": output_text[:4000],
            "step_index": state.get("step_index", 0),
            "next_action": f"{next_agent['name']} continues the task using the upstream output.",
        }

        try:
            async with get_db_context() as db:
                handoff = await handoff_repo.create(
                    db,
                    project_id=UUID(state["project_id"]),
                    run_id=UUID(self.run_id),
                    from_agent_id=UUID(str(agent_cfg["id"])),
                    to_agent_id=UUID(str(next_agent["id"])),
                    summary=summary[:5000],
                    package_json=package_json,
                )
                handoff = await handoff_repo.update(
                    db,
                    db_handoff=handoff,
                    update_data={"status": "sent"},
                )
                await db.commit()
                return str(handoff.id)
        except Exception as exc:
            logger.debug(
                "Failed to create handoff %s -> %s: %s", agent_cfg["name"], next_agent["name"], exc
            )
            return None

    def _dispatch_node(self, state: SupervisorState) -> dict:
        """Pop the next agent from the queue and set it as current_agent."""
        queue = list(state["agent_queue"])
        if not queue:
            return {"agent_queue": [], "current_agent": None}
        next_agent = queue.pop(0)
        return {"agent_queue": queue, "current_agent": next_agent}

    @staticmethod
    def _build_pipeline_prompt(
        agent_cfg: dict,
        step_index: int,
        original_task: str,
        last_output: str,
    ) -> str:
        """Build structured input for each agent in the pipeline (v2 data flow).

        Agent 0 receives the original task directly.
        Agent N>0 receives the previous agent's output as structured context,
        ensuring a proper data pipeline instead of every agent re-deriving
        from the same raw task.
        """
        if step_index == 0 or not last_output:
            return original_task

        role = agent_cfg.get("role", agent_cfg.get("name", "Agent"))
        return (
            f"## Previous Agent Output\n\n{last_output}\n\n"
            f"---\n\n"
            f"## Your Task ({role})\n\n{original_task}"
        )

    async def _run_agent_node(self, state: SupervisorState) -> dict:
        """Run the current agent via the fallback-aware runtime dispatcher."""
        agent_cfg = state.get("current_agent")
        if not agent_cfg:
            return {}

        from app.db.session import get_db_context
        from app.services.event_bus import AgentEvent, event_bus
        from app.services.model_fallback import run_with_fallback

        agent_name = agent_cfg["name"]
        agent_role = agent_cfg.get("role", "")
        project_id = state["project_id"]
        step_index = state.get("step_index", 0)
        pending_handoff_id = state.get("pending_handoff_id")

        if pending_handoff_id:
            await self._mark_handoff_received(pending_handoff_id)

        # v2: build structured pipeline prompt
        prompt = self._build_pipeline_prompt(
            agent_cfg=agent_cfg,
            step_index=step_index,
            original_task=state["task"],
            last_output=state.get("last_output", ""),
        )

        await event_bus.emit(
            AgentEvent(
                type="agent_started",
                project_id=project_id,
                run_id=self.run_id,
                task=state["task"],
                agent_name=agent_name,
                agent_role=agent_role,
            )
        )

        # Build a lightweight AgentConfig-like object for the runtime dispatcher
        class _AgentProxy:
            pass

        proxy = _AgentProxy()
        tc = agent_cfg.get("tools_config", {})
        proxy.runtime_kind = tc.get("runtime_kind") or tc.get("ai_backend") or "claude-cli"
        proxy.model = tc.get("model", "")
        proxy.max_tokens = agent_cfg.get("max_tokens", 2048)
        proxy.temperature = agent_cfg.get("temperature", 70)

        try:
            async with get_db_context() as db:
                text, meta = await run_with_fallback(
                    proxy,
                    prompt=prompt,
                    system_prompt=agent_cfg.get(
                        "system_prompt",
                        f"You are {agent_name}, a {agent_role}.",
                    ),
                    db=db,
                )
            new_handoff_id: str | None = None
            is_error = (
                text.startswith("[Agent error:")
                or text.startswith("[kimi-cli error")
                or text.startswith("[claude-cli error")
            )
            if is_error:
                await event_bus.emit(
                    AgentEvent(
                        type="agent_error",
                        project_id=project_id,
                        run_id=self.run_id,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        data=text[:500],
                    )
                )
            else:
                # Stream the output in chunks so the UI sees progress
                chunk_size = 120
                for i in range(0, len(text), chunk_size):
                    chunk = text[i : i + chunk_size]
                    await event_bus.emit(
                        AgentEvent(
                            type="agent_chunk",
                            project_id=project_id,
                            run_id=self.run_id,
                            agent_name=agent_name,
                            agent_role=agent_role,
                            data=chunk,
                        )
                    )
                await event_bus.emit(
                    AgentEvent(
                        type="agent_done",
                        project_id=project_id,
                        run_id=self.run_id,
                        agent_name=agent_name,
                        agent_role=agent_role,
                        data=text[:500],
                    )
                )
                next_agent = state["agent_queue"][0] if state.get("agent_queue") else None
                new_handoff_id: str | None = None
                if next_agent:
                    if self.run_id:
                        new_handoff_id = await self._create_handoff(
                            state=state,
                            agent_cfg=agent_cfg,
                            next_agent=next_agent,
                            output_text=text,
                        )
                    await event_bus.emit(
                        AgentEvent(
                            type="agent_handoff",
                            project_id=project_id,
                            run_id=self.run_id,
                            agent_name=agent_name,
                            agent_role=agent_role,
                            data=f"{agent_name} handed off to {next_agent['name']}",
                        )
                    )
            logger.info(
                "Agent '%s' (step %d) completed (error=%s)", agent_name, step_index, is_error
            )
            return {
                "step_index": step_index + 1,
                "last_output": text,
                "pending_handoff_id": None if is_error else new_handoff_id,
                "agent_results": {agent_name: text},
                "current_agent": None,
                "messages": [HumanMessage(content=f"[{agent_name}]: {text[:300]}")],
            }
        except Exception as exc:
            err_text = f"[Agent error: {exc}]"
            logger.exception("Agent '%s' (step %d) failed", agent_name, step_index)
            await event_bus.emit(
                AgentEvent(
                    type="agent_error",
                    project_id=project_id,
                    run_id=self.run_id,
                    agent_name=agent_name,
                    agent_role=agent_role,
                    data=err_text[:500],
                )
            )
            return {
                "step_index": step_index + 1,
                "last_output": err_text,
                "pending_handoff_id": None,
                "agent_results": {agent_name: err_text},
                "current_agent": None,
                "messages": [HumanMessage(content=f"[{agent_name}]: {err_text[:300]}")],
            }

    async def _aggregate_node(self, state: SupervisorState) -> dict:
        """Combine all agent results into the final response."""
        parts = []
        for cfg in self.agent_configs:
            name = cfg["name"]
            role = cfg.get("role", name)
            result = state["agent_results"].get(name, "*(no output)*")
            parts.append(f"## {name} — {role}\n\n{result}")
        final = "\n\n---\n\n".join(parts) if parts else "No agents produced output."
        return {"final_response": final}

    def _route_after_dispatch(self, state: SupervisorState) -> str:
        if state.get("current_agent"):
            return "run_agent"
        # Queue is empty — aggregate if we have results, else end
        if state.get("agent_results"):
            return "aggregate"
        return "__end__"

    def _initial_state(self, task: str, project_id: str) -> SupervisorState:
        return {
            "task": task,
            "project_id": project_id,
            "step_index": 0,
            "agent_queue": list(self.agent_configs),
            "current_agent": None,
            "pending_handoff_id": None,
            "last_output": "",
            "agent_results": {},
            "messages": [HumanMessage(content=task)],
            "final_response": None,
        }

    async def run(self, task: str, project_id: str) -> str:
        result = await self._graph.ainvoke(self._initial_state(task, project_id))
        return result.get("final_response") or "No agents produced output."

    async def stream_events(self, task: str, project_id: str):
        async for event in self._graph.astream(
            self._initial_state(task, project_id), stream_mode="updates"
        ):
            yield event
