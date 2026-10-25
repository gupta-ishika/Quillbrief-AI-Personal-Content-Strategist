import logging
from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool

from app.tools.database_tools import (
    load_channel_insights,
    load_latest_plan,
    save_plan_version,
)
from app.tools.mcp_adapter import MCPAdapter, mcp_adapter

logger = logging.getLogger(__name__)


def db_save_plan_tool(
    lineage_id: str,
    version: int,
    run_id: str,
    items: list[dict[str, Any]],
    status: str = "PENDING_APPROVAL",
    feedback_text: str | None = None,
) -> dict[str, Any]:
    """Persists a new content plan version with item objectives and source labels (ADR-029)."""
    return save_plan_version(
        lineage_id=lineage_id,
        version=version,
        run_id=run_id,
        items=items,
        created_by="strategist",
        status=status,
        feedback_text=feedback_text,
    )


def db_load_latest_plan_tool(
    lineage_id: str,
) -> dict[str, Any]:
    """Loads the latest content plan version and its items for a lineage."""
    return load_latest_plan(lineage_id=lineage_id)


def db_load_channel_insights_tool(
    channel_external_id: str,
) -> dict[str, Any]:
    """Loads existing comment insights for the connected channel."""
    return load_channel_insights(channel_external_id=channel_external_id)


def register_strategist_tools(adapter: MCPAdapter | None = None) -> None:
    """Registers the 3 strategist database tools in the MCP adapter."""
    target_adapter = adapter or mcp_adapter

    tools_to_register: list[tuple[str, str, Callable[..., Any]]] = [
        ("db_save_plan", "Persists a new plan version with items", db_save_plan_tool),
        (
            "db_load_latest_plan",
            "Loads latest plan version by lineage ID",
            db_load_latest_plan_tool,
        ),
        (
            "db_load_channel_insights",
            "Loads audience comment insights",
            db_load_channel_insights_tool,
        ),
    ]

    for name, desc, fn in tools_to_register:
        st = StructuredTool.from_function(func=fn, name=name, description=desc)
        target_adapter.register_tool(st, server_name="strategist")


# Automatically register strategist tools in global adapter
register_strategist_tools()
