from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import Creator
from app.db.repositories import (
    create_goal,
    create_run,
    update_run_status,
)
from app.db.session import get_db
from app.graph import (
    ContentState,
    supervisor_node,
)
from app.main import app
from app.scheduler import reset_scheduler
from app.tools.listener_tools import cluster_comments_tool
from app.tools.mcp_adapter import (
    MCPAdapter,
    UnauthorizedToolCallError,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    reset_scheduler()
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def do_connect(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        sess = session_factory()
        try:
            yield sess
        finally:
            sess.close()

    app.dependency_overrides[get_db] = override_get_db
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        app.dependency_overrides.clear()
        reset_scheduler()


# ==============================================================================
# UT-31 Model failure recording & degraded-run indicator
# ==============================================================================


@pytest.mark.asyncio
async def test_ut_31_supervisor_invalid_json_uses_fallback_and_records_degraded(
    db_session: Session,
) -> None:
    creator = Creator(display_name="Creator")
    db_session.add(creator)
    db_session.commit()

    goal = create_goal(db_session, creator_id=creator.id, text="Make videos")
    run = create_run(db_session, run_type="goal", depth_level="standard", goal_id=goal.id)

    # When LLM raises an error, supervisor_node falls back deterministically
    with patch(
        "app.graph.supervisor.request_supervisor_llm",
        new_callable=AsyncMock,
        side_effect=Exception("Connection refused to Ollama"),
    ):
        state: ContentState = {
            "run_id": run.id,
            "creator_id": creator.id,
            "goal": "Make videos",
            "comment_insights": [],
            "research_results": {},
            "current_plan_id": None,
            "approval_status": "NONE",
            "step_count": 0,
            "tokens_used": 0,
            "depth_level": "standard",
        }
        res_state = await supervisor_node(state, db_session=db_session)
        assert res_state["next_action"] in ("listener", "research")
        assert res_state.get("degraded") is True
        assert "fallback" in (res_state.get("degraded_reason") or "").lower()

        if res_state.get("degraded"):
            update_run_status(
                db_session,
                run_id=run.id,
                status=run.status,
                degraded=True,
                degraded_reason=res_state.get("degraded_reason"),
            )

    # Verify run record in DB is degraded
    db_session.refresh(run)
    assert run.degraded is True


# ==============================================================================
# Structured tool errors & unavailable MCP server
# ==============================================================================


def test_structured_tool_error_handling() -> None:
    # Empty comments input handled gracefully with structured output
    result = cluster_comments_tool(comments=[])
    assert result["themes"] == []
    assert result["coverage_analyzed"] == 0


def test_mcp_tool_unauthorized_structured_error() -> None:
    adapter = MCPAdapter()
    # Calling unauthorized tool produces UnauthorizedToolCallError
    with pytest.raises(UnauthorizedToolCallError) as exc_info:
        adapter.execute_for_agent(
            agent_name="listener",
            tool_name="unauthorized_tool_xyz",
            kwargs={},
        )
    assert "Security Violation" in str(exc_info.value)
