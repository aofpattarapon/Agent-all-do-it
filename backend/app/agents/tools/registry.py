"""Tool registry mapping agent permission names to callable tool definitions.

Permission names are stored on ``AgentConfig.tool_permissions`` and map here to
concrete tool callables, descriptions and JSON-ish parameter schemas. Use
``get_allowed_tools(tool_permissions)`` to resolve a permission list into the
set of tools an agent is allowed to use.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agents.tools.code_exec import execute_code
from app.agents.tools.db_query import run_query
from app.agents.tools.exchange_tool import get_fear_greed, get_market_data, place_order
from app.agents.tools.file_io import list_dir, read_file, write_file
from app.agents.tools.http_request import http_get, http_post
from app.agents.tools.web_search import web_search

#: Parameters that the agent runtime MUST inject from the run context and that
#: MUST NOT be accepted from the LLM (preventing an agent from widening its own
#: scope to another project). When the tool-dispatch loop is built, fill these
#: from context and reject any LLM-provided value for them. Schemas that contain
#: such a parameter advertise it via the ``x-runtime-injected`` key.
RUNTIME_INJECTED_PARAMS: frozenset[str] = frozenset({"project_id"})


@dataclass(frozen=True)
class ToolDef:
    """A registered agent tool."""

    name: str
    description: str
    func: Callable[..., Any]
    schema: dict[str, Any]


TOOL_REGISTRY: dict[str, ToolDef] = {
    "web_search": ToolDef(
        name="web_search",
        description="Search the web and return a list of {title, url, snippet}.",
        func=web_search,
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "max_results": {"type": "integer", "description": "Max results.", "default": 5},
            },
            "required": ["query"],
        },
    ),
    "code_exec": ToolDef(
        name="code_exec",
        description="Execute a Python code snippet in a subprocess (dev sandbox only).",
        func=execute_code,
        schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Source code to run."},
                "language": {"type": "string", "description": "Language.", "default": "python"},
                "timeout": {"type": "integer", "description": "Timeout seconds.", "default": 10},
            },
            "required": ["code"],
        },
    ),
    "file_read": ToolDef(
        name="file_read",
        description="Read a file or list a directory inside the project sandbox.",
        func=read_file,
        schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project id (sandbox scope)."},
                "path": {"type": "string", "description": "Relative path within the sandbox."},
            },
            "required": ["path"],
            "x-runtime-injected": ["project_id"],
        },
    ),
    "file_write": ToolDef(
        name="file_write",
        description="Write a text file inside the project sandbox.",
        func=write_file,
        schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project id (sandbox scope)."},
                "path": {"type": "string", "description": "Relative path within the sandbox."},
                "content": {"type": "string", "description": "File contents."},
            },
            "required": ["path", "content"],
            "x-runtime-injected": ["project_id"],
        },
    ),
    "db_query": ToolDef(
        name="db_query",
        description=(
            "Read-only, project-scoped database access. Preferred: pass 'table' "
            "(a project-scoped table) with optional 'columns'/'filters'. Advanced: "
            "pass a single 'sql' SELECT that filters by project_id. Cross-project "
            "reads and any writes are blocked. Returns up to 100 rows."
        ),
        func=run_query,
        schema={
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "Project-scoped table to read (structured mode).",
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional column allowlist for structured mode.",
                },
                "filters": {
                    "type": "object",
                    "description": "Optional {column: value} equality filters.",
                },
                "sql": {
                    "type": "string",
                    "description": "Advanced: a single SELECT that filters by project_id.",
                },
                "limit": {"type": "integer", "description": "Max rows (<=100).", "default": 50},
            },
            "required": [],
            # project_id is injected by the runtime from the run context, never
            # by the LLM. See RUNTIME_INJECTED_PARAMS below.
            "x-runtime-injected": ["project_id"],
        },
    ),
    "http_get": ToolDef(
        name="http_get",
        description="Perform an HTTP GET request to an external URL and return the JSON/text response.",
        func=http_get,
        schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to request (including protocol)."},
                "headers": {"type": "object", "description": "Optional request headers.", "default": {}},
                "params": {"type": "object", "description": "Optional query parameters.", "default": {}},
                "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 30},
            },
            "required": ["url"],
        },
    ),
    "http_post": ToolDef(
        name="http_post",
        description="Perform an HTTP POST request with a JSON body to an external URL.",
        func=http_post,
        schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to request (including protocol)."},
                "body": {"type": "object", "description": "JSON body to send.", "default": {}},
                "headers": {"type": "object", "description": "Optional request headers.", "default": {}},
                "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 30},
            },
            "required": ["url"],
        },
    ),
    "api_call": ToolDef(
        name="api_call",
        description="Alias for http_get — make an outbound HTTP GET request.",
        func=http_get,
        schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to request."},
                "headers": {"type": "object", "description": "Optional request headers.", "default": {}},
                "params": {"type": "object", "description": "Optional query parameters.", "default": {}},
            },
            "required": ["url"],
        },
    ),
    "exchange_place_order": ToolDef(
        name="exchange_place_order",
        description="Place a crypto order through the exchange safety wrapper in paper, testnet, or live mode.",
        func=place_order,
        schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading symbol, e.g. BTC/USDT."},
                "side": {"type": "string", "description": "buy or sell."},
                "amount": {"type": "number", "description": "Base asset amount to trade."},
                "order_type": {"type": "string", "description": "market or limit.", "default": "market"},
                "price": {"type": "number", "description": "Optional limit or reference price."},
                "stop_loss": {"type": "number", "description": "Optional stop-loss price."},
                "take_profits": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Optional take-profit ladder prices.",
                    "default": [],
                },
                "exchange_name": {"type": "string", "description": "Exchange slug.", "default": "binance"},
            },
            "required": ["symbol", "side", "amount"],
        },
    ),
    "exchange_market_data": ToolDef(
        name="exchange_market_data",
        description="Fetch current market price, funding rate, and long/short ratio for a symbol.",
        func=get_market_data,
        schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Trading symbol, e.g. BTCUSDT or BTC/USDT."},
                "exchange_name": {"type": "string", "description": "Exchange slug.", "default": "binance"},
            },
            "required": ["symbol"],
        },
    ),
    "fear_greed_index": ToolDef(
        name="fear_greed_index",
        description="Fetch the latest crypto Fear & Greed index.",
        func=get_fear_greed,
        schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
}

# Companion file tools that share the "file_write" permission for directory ops.
_FILE_LIST = ToolDef(
    name="list_dir",
    description="List directory entries inside the project sandbox.",
    func=list_dir,
    schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "Project id (sandbox scope)."},
            "path": {"type": "string", "description": "Relative directory path.", "default": "."},
        },
        "required": [],
        "x-runtime-injected": ["project_id"],
    },
)


def get_allowed_tools(tool_permissions: list[str]) -> list[ToolDef]:
    """Resolve a permission list into the tools an agent may use.

    Unknown permission names are ignored. When ``file_read`` or ``file_write``
    is granted, the directory-listing tool is also included.
    """
    allowed: list[ToolDef] = []
    seen: set[str] = set()
    for perm in tool_permissions or []:
        tool = TOOL_REGISTRY.get(perm)
        if tool is not None and tool.name not in seen:
            allowed.append(tool)
            seen.add(tool.name)
    if ("file_read" in (tool_permissions or []) or "file_write" in (tool_permissions or [])) and (
        _FILE_LIST.name not in seen
    ):
        allowed.append(_FILE_LIST)
        seen.add(_FILE_LIST.name)
    return allowed
