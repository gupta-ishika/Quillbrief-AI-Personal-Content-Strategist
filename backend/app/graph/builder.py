"""Content graph builder connecting Supervisor, ReAct agents, Writer-Critic loop, and Approval node."""

from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.critic import critic_node
from app.agents.listener import listener_node
from app.agents.research import research_node
from app.agents.strategist import strategist_node
from app.agents.writer import writer_node
from app.graph.approval import approval_node
from app.graph.state import ContentState
from app.graph.supervisor import supervisor_node


def route_from_supervisor(state: ContentState) -> str:
    """Extracts next node decided by Supervisor, mapping to valid node or END."""
    action = state.get("next_action", "END")
    if action in ("listener", "research", "strategist", "writer", "approval"):
        return action
    return END


def route_from_critic(state: ContentState) -> str:
    """Routes from Critic: back to writer for revision, or to approval when passed/exhausted."""
    action = state.get("next_action")
    if action == "writer":
        return "writer"
    return "approval"


def create_content_graph(
    checkpointer: Any = None,
    db_session: Session | None = None,
) -> Any:
    """Builds and compiles the StateGraph for Phase 2.

    Topology (ARCHITECTURE.md Section 3.2):
    - START -> supervisor
    - supervisor -> [listener, research, strategist, writer, approval, END]
    - listener -> supervisor
    - research -> supervisor
    - strategist -> supervisor
    - writer -> critic
    - critic -> writer (revision loop) | approval (passed or limit reached)
    - approval -> supervisor
    """
    workflow = StateGraph(ContentState)

    # 1. Register nodes with bound db_session
    async def bound_supervisor(state: ContentState) -> dict[str, Any]:
        return await supervisor_node(state, db_session=db_session)

    async def bound_listener(state: ContentState) -> dict[str, Any]:
        return await listener_node(state, db_session=db_session)

    async def bound_research(state: ContentState) -> dict[str, Any]:
        return await research_node(state, db_session=db_session)

    async def bound_strategist(state: ContentState) -> dict[str, Any]:
        return await strategist_node(state, db_session=db_session)

    async def bound_writer(state: ContentState) -> dict[str, Any]:
        return await writer_node(state, db_session=db_session)

    async def bound_critic(state: ContentState) -> dict[str, Any]:
        return await critic_node(state, db_session=db_session)

    def bound_approval(state: ContentState) -> dict[str, Any]:
        return approval_node(state, db_session=db_session)

    workflow.add_node("supervisor", bound_supervisor)
    workflow.add_node("listener", bound_listener)
    workflow.add_node("research", bound_research)
    workflow.add_node("strategist", bound_strategist)
    workflow.add_node("writer", bound_writer)
    workflow.add_node("critic", bound_critic)
    workflow.add_node("approval", bound_approval)

    # 2. Register edges
    workflow.add_edge(START, "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "listener": "listener",
            "research": "research",
            "strategist": "strategist",
            "writer": "writer",
            "approval": "approval",
            END: END,
        },
    )

    workflow.add_edge("listener", "supervisor")
    workflow.add_edge("research", "supervisor")
    workflow.add_edge("strategist", "supervisor")
    workflow.add_edge("writer", "critic")

    workflow.add_conditional_edges(
        "critic",
        route_from_critic,
        {
            "writer": "writer",
            "approval": "approval",
        },
    )

    workflow.add_edge("approval", "supervisor")

    # 3. Compile with checkpointer
    return workflow.compile(checkpointer=checkpointer)
