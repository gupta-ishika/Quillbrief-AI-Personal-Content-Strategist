import logging
from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool

from app.db.base import utc_now
from app.db.models import Approval
from app.db.session import SessionLocal
from app.tools.mcp_adapter import MCPAdapter, mcp_adapter

logger = logging.getLogger(__name__)


def approval_tool_func(
    item_id: str,
    item_type: str = "plan",
    decision: str | None = None,
    feedback_text: str | None = None,
) -> dict[str, Any]:
    """Inspects or records human approval state for a plan, draft, or depth increase (HITL-01)."""
    with SessionLocal() as db:
        approval = (
            db.query(Approval)
            .filter_by(item_id=item_id)
            .order_by(Approval.requested_at.desc())
            .first()
        )
        if not approval:
            return {
                "item_id": item_id,
                "item_type": item_type,
                "status": "NONE",
                "source": "approval_tool",
                "timestamp": utc_now().isoformat(),
                "verified": True,
            }

        return {
            "approval_id": approval.id,
            "item_id": approval.item_id,
            "item_type": approval.item_type,
            "status": approval.status,
            "decision": approval.decision,
            "feedback_text": approval.feedback_text,
            "requested_at": approval.requested_at.isoformat() if approval.requested_at else None,
            "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
            "source": "approval_tool",
            "timestamp": utc_now().isoformat(),
            "verified": True,
        }


def register_approval_tools(adapter: MCPAdapter | None = None) -> None:
    """Registers the approval_tool in the specified or global MCP adapter."""
    target_adapter = adapter or mcp_adapter

    tools_to_register: list[tuple[str, str, Callable[..., Any]]] = [
        ("approval_tool", "Checks or records human approval state", approval_tool_func),
    ]

    for name, desc, fn in tools_to_register:
        st = StructuredTool.from_function(func=fn, name=name, description=desc)
        target_adapter.register_tool(st, server_name="approval")


# Automatically register approval tool in global adapter
register_approval_tools()
