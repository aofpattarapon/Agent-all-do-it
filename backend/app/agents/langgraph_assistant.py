
"""LangGraph ReAct Agent implementation.

A simple ReAct (Reasoning + Acting) agent built with LangGraph.
Uses a graph-based architecture with conditional edges for tool execution.
"""

import logging
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.prompts import DEFAULT_SYSTEM_PROMPT
from app.agents.tools import get_current_datetime
from app.core.config import settings

logger = logging.getLogger(__name__)


class AgentContext(TypedDict, total=False):
    """Runtime context for the agent.

    Passed via config parameter to the graph.
    """

    user_id: str | None
    user_name: str | None
    metadata: dict[str, Any]


class AgentState(TypedDict):
    """State for the LangGraph agent.

    This is what flows through the agent graph.
    The messages field uses add_messages reducer to properly
    append new messages to the conversation history.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    remaining_steps: RemainingSteps


@tool
def current_datetime() -> dict[str, str]:
    """Get the current date and time.

    Use this tool when you need to know the current date or time.
    """
    return get_current_datetime()


# List of all available tools
ALL_TOOLS = [current_datetime]


class LangGraphAssistant:
    """ReAct agent wrapper using LangGraph.

    Implements a graph-based agent with:
    - An agent node that processes messages and decides actions
    - A tools node that executes tool calls
    - Conditional edges that loop back for tool execution or end

    The ReAct pattern:
    1. Agent receives input and reasons about it
    2. If tool calls are needed, execute them
    3. Tool results are added to messages
    4. Agent reasons again with new information
    5. Repeat until agent provides final response
    """

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        thinking_effort: str | None = None,
    ):
        self.model_name = model_name or settings.AI_MODEL
        self.temperature = temperature or settings.AI_TEMPERATURE
        # Extended-thinking effort for reasoning-capable models (Claude
        # extended thinking, OpenAI o-series). ``None`` keeps the model in
        # plain mode.
        self.thinking_effort = (
            thinking_effort
            if thinking_effort is not None
            else (settings.AI_THINKING_EFFORT if settings.AI_THINKING_ENABLED else None)
        )
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._model = self._create_model()
        self._graph = None
        self._checkpointer = MemorySaver()

    def _create_model(self) -> BaseChatModel:
        """Create the LLM model with tools bound."""
        # AI_MODEL may be "provider/model-name" or bare "model-name".
        # Split provider prefix so each SDK receives only the model id.
        if "/" in self.model_name:
            provider_prefix, model_id = self.model_name.split("/", 1)
            provider = provider_prefix.lower()
        else:
            model_id = self.model_name
            provider = self.model_name.lower()

        if provider == "anthropic" or model_id.lower().startswith("claude"):
            anthropic_kwargs: dict[str, Any] = {}
            if self.thinking_effort:
                budget = {"low": 1024, "medium": 4096, "high": 16384}.get(self.thinking_effort, 4096)
                anthropic_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
                anthropic_kwargs["max_tokens"] = budget + 4096
                anthropic_kwargs["temperature"] = 1.0
            model = ChatAnthropic(
                model=model_id,
                temperature=anthropic_kwargs.pop("temperature", self.temperature),
                api_key=settings.ANTHROPIC_API_KEY,
                **anthropic_kwargs,
            )
        elif provider in ("google", "google-genai") or model_id.lower().startswith("gemini"):
            model = ChatGoogleGenerativeAI(
                model=model_id,
                temperature=self.temperature,
                google_api_key=settings.GOOGLE_API_KEY,
            )
        else:
            openai_kwargs: dict[str, Any] = {}
            if self.thinking_effort:
                openai_kwargs["reasoning"] = {"effort": self.thinking_effort, "summary": "auto"}
                openai_kwargs["use_responses_api"] = True
                openai_kwargs["output_version"] = "responses/v1"
            model = ChatOpenAI(
                model=model_id,
                temperature=self.temperature,
                api_key=settings.OPENAI_API_KEY,
                **openai_kwargs,
            )

        return model.bind_tools(ALL_TOOLS)

    async def _agent_node(self, state: AgentState) -> dict[str, list[AnyMessage]]:
        """Agent node that processes messages and decides whether to call tools.

        This is the main reasoning node in the ReAct pattern.
        """
        if state.get("remaining_steps", 10) <= 2:
            return {"messages": [AIMessage(content="I've reached my step limit and cannot continue reasoning. Here is what I found so far.")]}

        # Prepend system message to the conversation
        messages = [SystemMessage(content=self.system_prompt), *state["messages"]]

        response = await self._model.ainvoke(messages)

        logger.info(
            f"Agent processed message - Tool calls: {len(response.tool_calls) if hasattr(response, 'tool_calls') else 0}"
        )

        return {"messages": [response]}

    def _should_continue(self, state: AgentState) -> Literal["tools", "__end__"]:
        """Conditional edge that decides whether to continue to tools or end.

        Returns:
            - "tools" if the agent made tool calls (needs to execute tools)
            - "__end__" if the agent provided a final response (no tool calls)
        """
        messages = state["messages"]
        last_message = messages[-1]

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            logger.info(f"Continuing to tools - {len(last_message.tool_calls)} tool(s) to execute")
            return "tools"

        logger.info("No tool calls - ending conversation")
        return "__end__"

    def _build_graph(self) -> CompiledStateGraph:
        """Build and compile the LangGraph state graph."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("agent", self._agent_node)
        workflow.add_node("tools", ToolNode(ALL_TOOLS))

        # Add edges
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {"tools": "tools", "__end__": END},
        )
        workflow.add_edge("tools", "agent")

        return workflow.compile(checkpointer=self._checkpointer)

    @property
    def graph(self) -> CompiledStateGraph:
        """Get or create the compiled graph instance."""
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    @staticmethod
    def _convert_history(
        history: list[dict[str, str]] | None,
    ) -> list[HumanMessage | AIMessage | SystemMessage]:
        """Convert conversation history to LangChain message format."""
        messages: list[HumanMessage | AIMessage | SystemMessage] = []

        for msg in history or []:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "system":
                messages.append(SystemMessage(content=msg["content"]))

        return messages

    async def run(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        context: AgentContext | None = None,
        thread_id: str = "default",
    ) -> tuple[str, list[Any], AgentContext]:
        """Run agent and return the output along with tool call events.

        Args:
            user_input: User's message.
            history: Conversation history as list of {"role": "...", "content": "..."}.
            context: Optional runtime context with user info.
            thread_id: Thread ID for conversation continuity.

        Returns:
            Tuple of (output_text, tool_events, context).
        """
        messages = self._convert_history(history)
        messages.append(HumanMessage(content=user_input))

        agent_context: AgentContext = context if context is not None else {}

        logger.info(f"Running agent with user input: {user_input[:100]}...")

        config = {
            "configurable": {
                "thread_id": thread_id,
                **agent_context,
            }
        }
        result = await self.graph.ainvoke({"messages": messages}, config=config)

        # Extract the final response and tool events
        output = ""
        tool_events: list[Any] = []

        for message in result.get("messages", []):
            if isinstance(message, AIMessage):
                if message.content:
                    output = message.content if isinstance(message.content, str) else str(message.content)
                if hasattr(message, "tool_calls") and message.tool_calls:
                    tool_events.extend(message.tool_calls)

        logger.info(f"Agent run complete. Output length: {len(output)} chars")

        return output, tool_events, agent_context

    async def stream(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        context: AgentContext | None = None,
        thread_id: str = "default",
    ):
        """Stream agent execution with message and state update streaming.

        Args:
            user_input: User's message.
            history: Conversation history.
            context: Optional runtime context.
            thread_id: Thread ID for conversation continuity.

        Yields:
            Tuples of (stream_mode, data) for streaming responses.
            - stream_mode="messages": (chunk, metadata) for LLM tokens
            - stream_mode="updates": state updates after each node
        """
        messages = self._convert_history(history)
        messages.append(HumanMessage(content=user_input))

        agent_context: AgentContext = context if context is not None else {}

        config = {
            "configurable": {
                "thread_id": thread_id,
                **agent_context,
            }
        }

        logger.info(f"Starting stream for user input: {user_input[:100]}...")
        async for stream_mode, data in self.graph.astream(
            {"messages": messages},
            config=config,
            stream_mode=["messages", "updates"],
        ):
            yield stream_mode, data


def get_agent(
    model_name: str | None = None,
    thinking_effort: str | None = None,
) -> LangGraphAssistant:
    """Factory function to create a LangGraphAssistant.

    Args:
        model_name: Override the default AI model.
        thinking_effort: Extended-thinking effort ("low"/"medium"/"high") or
            ``None`` to disable. Wired to ``thinking={...}`` for Anthropic and
            ``reasoning={...}`` for OpenAI Responses-API models.

    Returns:
        Configured LangGraphAssistant instance.
    """
    return LangGraphAssistant(model_name=model_name, thinking_effort=thinking_effort)


async def run_agent(
    user_input: str,
    history: list[dict[str, str]],
    context: AgentContext | None = None,
    thread_id: str = "default",
) -> tuple[str, list[Any], AgentContext]:
    """Run agent and return the output along with tool call events.

    This is a convenience function for backwards compatibility.

    Args:
        user_input: User's message.
        history: Conversation history.
        context: Optional runtime context.
        thread_id: Thread ID for conversation continuity.

    Returns:
        Tuple of (output_text, tool_events, context).
    """
    agent = get_agent()
    return await agent.run(user_input, history, context, thread_id)
