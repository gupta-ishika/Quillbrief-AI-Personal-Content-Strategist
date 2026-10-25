import pytest
from langchain_core.tools import tool

from app.tools.mcp_adapter import (
    AGENT_TOOL_ALLOWLISTS,
    MCPAdapter,
    UnauthorizedToolCallError,
    verify_result_provenance,
)


@tool
def sample_fetch_comments(video_id: str) -> dict[str, str]:
    """Sample comment fetching tool."""
    return {"status": "ok", "video_id": video_id}


@tool
def sample_web_search(query: str) -> dict[str, str]:
    """Sample web search tool."""
    return {"results": f"Found results for {query}"}


@tool
def sample_db_save_plan(plan_data: str) -> dict[str, str]:
    """Sample plan saving tool."""
    return {"saved": True, "plan": plan_data}


@tool
def sample_state_update(key: str, value: str) -> dict[str, str]:
    """Sample state update tool."""
    return {key: value}


def test_agent_tool_allowlists_defined() -> None:
    """RULES.md / ARCHITECTURE.md: Defined tool allowlists per agent."""
    expected_agents = {
        "supervisor",
        "listener",
        "research",
        "strategist",
        "writer",
        "critic",
        "repurposer",
        "analyst",
        "approval",
    }
    assert expected_agents.issubset(set(AGENT_TOOL_ALLOWLISTS.keys()))

    # Supervisor must only have state/task tools, no external tools
    supervisor_tools = AGENT_TOOL_ALLOWLISTS["supervisor"]
    assert "web_search" not in supervisor_tools
    assert "fetch_comments" not in supervisor_tools
    assert "state_update" in supervisor_tools


def test_get_agent_tools_filtering() -> None:
    """UT-32: Each agent receives only its own tools."""
    adapter = MCPAdapter()
    adapter.register_tool(sample_fetch_comments, server_name="youtube")
    adapter.register_tool(sample_web_search, server_name="search")
    adapter.register_tool(sample_db_save_plan, server_name="db")
    adapter.register_tool(sample_state_update, server_name="internal")

    # Rename tools to match allowlist names
    sample_fetch_comments.name = "fetch_comments"
    sample_web_search.name = "web_search"
    sample_db_save_plan.name = "db_save_plan"
    sample_state_update.name = "state_update"

    # Re-register with correct names
    adapter = MCPAdapter()
    adapter.register_tool(sample_fetch_comments, server_name="youtube")
    adapter.register_tool(sample_web_search, server_name="search")
    adapter.register_tool(sample_db_save_plan, server_name="db")
    adapter.register_tool(sample_state_update, server_name="internal")

    listener_tools = [t.name for t in adapter.get_agent_tools("listener")]
    assert "fetch_comments" in listener_tools
    assert "web_search" not in listener_tools
    assert "db_save_plan" not in listener_tools

    research_tools = [t.name for t in adapter.get_agent_tools("research")]
    assert "web_search" in research_tools
    assert "fetch_comments" not in research_tools

    strategist_tools = [t.name for t in adapter.get_agent_tools("strategist")]
    assert "db_save_plan" in strategist_tools
    assert "web_search" not in strategist_tools


def test_unauthorized_tool_call_refused_and_logged() -> None:
    """UT-32 / RULES.md: Call to a tool outside allowlist is refused and logged."""
    adapter = MCPAdapter()
    sample_web_search.name = "web_search"
    adapter.register_tool(sample_web_search, server_name="search")

    # Listener attempts to call web_search (which is only for Research)
    with pytest.raises(UnauthorizedToolCallError) as exc_info:
        adapter.execute_for_agent("listener", "web_search", {"query": "tech trends"})

    assert "not in allowlist for agent 'listener'" in str(exc_info.value)

    # Verify security audit log was recorded
    assert len(adapter.audit_logs) == 1
    log_entry = adapter.audit_logs[0]
    assert log_entry["event"] == "unauthorized_tool_call"
    assert log_entry["agent"] == "listener"
    assert log_entry["tool"] == "web_search"
    assert log_entry["allowed"] is False
    assert "timestamp" in log_entry


def test_authorized_tool_call_attaches_provenance() -> None:
    """UT-32: Every result carries source, timestamp, and verification flag."""
    adapter = MCPAdapter()
    sample_web_search.name = "web_search"
    adapter.register_tool(sample_web_search, server_name="brave_search")

    res = adapter.execute_for_agent("research", "web_search", {"query": "python 3.13"})
    assert res["source"] == "tool:brave_search:web_search"
    assert "timestamp" in res
    assert res["verified"] is True
    assert "results" in res


def test_verify_result_provenance() -> None:
    """UT-32: Results without source and timestamp are unverified."""
    valid_res = {"data": "123", "source": "database", "timestamp": "2026-10-25T10:00:00Z"}
    assert verify_result_provenance(valid_res) is True

    # Missing source
    assert verify_result_provenance({"data": "123", "timestamp": "2026-10-25T10:00:00Z"}) is False

    # Missing timestamp
    assert verify_result_provenance({"data": "123", "source": "database"}) is False

    # Non-dict
    assert verify_result_provenance("plain string") is False
