import logging
from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from app.db.base import utc_now

logger = logging.getLogger(__name__)

# Strict per-agent tool allowlists (UT-32, ARCHITECTURE.md Section 5, RULES.md)
AGENT_TOOL_ALLOWLISTS: dict[str, set[str]] = {
    "supervisor": {
        "state_update",
        "task_list_update",
    },
    "listener": {
        "fetch_comments",
        "cluster_comments",
        "db_save_content_item",
        "db_save_comment_insights",
        "db_load_channel_insights",
        "youtube_channel_lookup",
        "youtube_video_list",
    },
    "research": {
        "web_search",
        "web_fetch",
        "youtube_video_search",
        "youtube_channel_lookup",
    },
    "strategist": {
        "db_load_channel_insights",
        "db_save_plan",
        "db_load_latest_plan",
    },
    "writer": {
        "db_save_draft",
        "db_load_draft",
        "db_load_latest_plan",
    },
    "critic": {
        "draft_checker",
        "db_save_evaluation",
    },
    "repurposer": {
        "db_save_draft",
        "db_load_draft",
        "instagram_read_context",
    },
    "analyst": {
        "metrics_calculator",
        "youtube_analytics",
        "db_load_metrics",
        "db_save_metrics",
    },
    "approval": {
        "approval_tool",
    },
}


class ToolProvenance(BaseModel):
    source: str
    timestamp: str
    platform: str | None = None
    video_id: str | None = None
    verified: bool = True


class MCPToolSchema(BaseModel):
    name: str
    description: str
    server_name: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionError(Exception):
    pass


class UnauthorizedToolCallError(Exception):
    pass


def annotate_provenance(
    result: dict[str, Any],
    source: str,
    platform: str | None = None,
    video_id: str | None = None,
) -> dict[str, Any]:
    """Ensures every tool result carries provenance metadata (UT-32)."""
    if not isinstance(result, dict):
        return {
            "data": result,
            "source": source,
            "timestamp": utc_now().isoformat(),
            "platform": platform,
            "video_id": video_id,
            "verified": True,
        }

    res_copy = dict(result)
    res_copy["source"] = res_copy.get("source") or source
    res_copy["timestamp"] = res_copy.get("timestamp") or utc_now().isoformat()
    if platform:
        res_copy["platform"] = res_copy.get("platform") or platform
    if video_id:
        res_copy["video_id"] = res_copy.get("video_id") or video_id
    res_copy["verified"] = True
    return res_copy


def verify_result_provenance(result: Any) -> bool:
    """Verifies that a tool result carries source and timestamp (UT-32).

    Results without them are rejected or marked unverified.
    """
    if not isinstance(result, dict):
        return False
    has_source = bool(result.get("source"))
    has_timestamp = bool(result.get("timestamp"))
    return has_source and has_timestamp


class MCPAdapter:
    """Manages MCP server tool conversion, allowlist enforcement, and provenance tracking."""

    def __init__(self) -> None:
        self._registered_tools: dict[str, BaseTool] = {}
        self._server_names: dict[str, str] = {}
        self._audit_logs: list[dict[str, Any]] = []

    def register_tool(self, tool_instance: BaseTool, server_name: str = "internal") -> None:
        """Registers a tool with an associated server/source name."""
        self._registered_tools[tool_instance.name] = tool_instance
        self._server_names[tool_instance.name] = server_name
        logger.debug("Registered tool '%s' from source '%s'.", tool_instance.name, server_name)

    def register_mcp_function(
        self,
        name: str,
        description: str,
        fn: Callable[..., Any],
        server_name: str,
    ) -> BaseTool:
        """Creates and registers a LangChain StructuredTool from an MCP function."""

        def wrapped_fn(**kwargs: Any) -> Any:
            res = fn(**kwargs)
            # Annotate with MCP provenance
            if isinstance(res, dict):
                return annotate_provenance(res, source=f"mcp:{server_name}")
            return annotate_provenance({"data": res}, source=f"mcp:{server_name}")

        structured_tool = StructuredTool.from_function(
            func=wrapped_fn,
            name=name,
            description=description,
        )
        self.register_tool(structured_tool, server_name=server_name)
        return structured_tool

    def get_tool(self, tool_name: str) -> BaseTool | None:
        return self._registered_tools.get(tool_name)

    def get_agent_tools(self, agent_name: str) -> list[BaseTool]:
        """Returns only the tools authorized for the specified agent (UT-32)."""
        allowed_names = AGENT_TOOL_ALLOWLISTS.get(agent_name.lower(), set())
        return [
            tool_obj for name, tool_obj in self._registered_tools.items() if name in allowed_names
        ]

    def execute_for_agent(
        self,
        agent_name: str,
        tool_name: str,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Executes a tool call on behalf of an agent, strictly enforcing allowlists (UT-32)."""
        clean_agent = agent_name.lower()
        allowed_names = AGENT_TOOL_ALLOWLISTS.get(clean_agent, set())

        # 1. Allowlist enforcement
        if tool_name not in allowed_names:
            error_msg = f"Security Violation: Tool '{tool_name}' is not in allowlist for agent '{agent_name}'."
            logger.warning(error_msg)
            self._audit_logs.append(
                {
                    "event": "unauthorized_tool_call",
                    "agent": agent_name,
                    "tool": tool_name,
                    "timestamp": utc_now().isoformat(),
                    "allowed": False,
                }
            )
            raise UnauthorizedToolCallError(error_msg)

        tool_obj = self._registered_tools.get(tool_name)
        if not tool_obj:
            raise ToolExecutionError(f"Tool '{tool_name}' is not registered in MCP adapter.")

        # 2. Execution
        try:
            raw_result = tool_obj.invoke(kwargs)
        except Exception as e:
            logger.error("Tool '%s' execution failed: %s", tool_name, e)
            raise ToolExecutionError(f"Tool '{tool_name}' failed: {e}") from e

        # 3. Provenance attachment and validation
        server_name = self._server_names.get(tool_name, "custom")
        annotated = annotate_provenance(
            raw_result if isinstance(raw_result, dict) else {"data": raw_result},
            source=f"tool:{server_name}:{tool_name}",
        )

        if not verify_result_provenance(annotated):
            annotated["verified"] = False
            logger.warning("Tool result for '%s' could not be fully verified.", tool_name)

        return annotated

    @property
    def audit_logs(self) -> list[dict[str, Any]]:
        return list(self._audit_logs)


# Default global MCP adapter instance
mcp_adapter = MCPAdapter()
