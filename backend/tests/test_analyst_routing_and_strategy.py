from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.agents.analyst import analyst_node
from app.agents.strategist import strategist_node
from app.db.base import Base
from app.db.repositories import (
    create_draft_version,
    create_goal,
    create_performance_metric,
    create_run,
    get_active_strategy_entries,
    get_or_create_creator,
    get_strategy_history,
    update_draft_status,
)
from app.graph.builder import create_content_graph, route_from_supervisor
from app.graph.state import ContentState
from app.graph.supervisor import calculate_eligible_nodes, decompose_goal_to_tasks


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(test_engine)


def test_supervisor_routes_to_analyst_for_analytics_goals() -> None:
    """GRAPH-10: Supervisor routes to Analyst for post-mortem / analytics goals."""
    goal_text = "Post-mortem analysis on recent video metrics and retention"
    tasks = decompose_goal_to_tasks(goal_text)
    assert len(tasks) >= 2
    assert tasks[0]["agent"] == "analyst"

    state: ContentState = {
        "run_type": "post_mortem",
        "user_goal": goal_text,
        "task_list": tasks,
        "performance_insights": {},
        "analyst_findings": [],
        "approval_status": "NONE",
    }

    eligible = calculate_eligible_nodes(state)
    assert eligible == ["analyst"]


def test_route_from_supervisor_allows_analyst() -> None:
    """GRAPH-10: route_from_supervisor correctly recognizes 'analyst' as a valid route."""
    state: ContentState = {"next_action": "analyst"}
    assert route_from_supervisor(state) == "analyst"


def test_supervisor_routes_findings_to_strategist() -> None:
    """GRAPH-10: When analyst findings exist and no content plan is made, supervisor routes to Strategist."""
    state: ContentState = {
        "run_type": "goal",
        "user_goal": "Optimize video strategy",
        "performance_insights": {"summary": "Analysis complete"},
        "analyst_findings": [
            {
                "finding": "Hooks in first 5s improve retention by 40%",
                "recommendation": "Lead with direct question",
                "confidence": "high",
                "sample_size": 15,
            }
        ],
        "current_plan_id": None,
        "approval_status": "NONE",
    }

    eligible = calculate_eligible_nodes(state)
    assert eligible == ["strategist"]


@pytest.mark.asyncio
async def test_strategist_incorporates_findings_and_stores_strategy(db_session: Session) -> None:
    """IT-08: Findings change the plan and Strategist stores strategy changes in strategy_entries."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Strategy optimization")
    run = create_run(db_session, run_type="goal", goal_id=goal.id)

    findings = [
        {
            "finding": "Tutorials with quick code examples hold 35% higher watch time",
            "recommendation": "Open with 15-second code preview before theory",
            "confidence": "high",
            "sample_size": 12,
            "evidence_json": {"avg_view_duration": 480.0},
        }
    ]

    state: ContentState = {
        "run_id": run.id,
        "run_type": "goal",
        "depth_level": "standard",
        "user_goal": "Create a tutorial series",
        "creator_profile": {"creator_id": creator.id, "niche": "Python Dev", "tone_preset": "technical"},
        "analyst_findings": findings,
        "performance_insights": {"findings_count": 1},
        "tokens_used": 0,
        "execution_steps": 1,
    }

    # Execute Strategist with fallback
    with patch("app.agents.strategist.request_strategist_llm", AsyncMock(side_effect=Exception("Model unavailable"))):
        output = await strategist_node(state, db_session=db_session)

    # 1. Output plan reflects the finding (IT-08)
    plan_items = output["content_plan"]
    assert len(plan_items) >= 1
    # Check that finding is incorporated in the reasons
    reasons = [it["reason"] for it in plan_items]
    assert any("Tutorials with quick code examples" in r or "finding" in r.lower() for r in reasons)

    # 2. Strategy entry is stored in database (GRAPH-10)
    active_strategies = get_active_strategy_entries(db_session, creator.id)
    assert len(active_strategies) == 1
    assert active_strategies[0].key == "post_mortem_1"
    assert "Tutorials with quick code examples" in active_strategies[0].value_json["finding"]
    assert "Adopted recommendation" in active_strategies[0].reason

    # 3. Strategy is returned in state
    assert "strategy" in output
    assert "post_mortem_1" in output["strategy"]


@pytest.mark.asyncio
async def test_subsequent_finding_supersedes_strategy_lineage(db_session: Session) -> None:
    """GRAPH-10: Successive post-mortem findings update strategy entries, preserving lineage."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Iterative strategy")
    run1 = create_run(db_session, run_type="goal", goal_id=goal.id)

    # Run 1: First finding
    state1: ContentState = {
        "run_id": run1.id,
        "run_type": "goal",
        "depth_level": "standard",
        "user_goal": "Channel growth",
        "creator_profile": {"creator_id": creator.id, "niche": "Cloud Engineering"},
        "analyst_findings": [
            {
                "finding": "Case studies have 2x shares",
                "recommendation": "Publish weekly case studies",
                "confidence": "moderate",
                "sample_size": 6,
            }
        ],
    }

    with patch("app.agents.strategist.request_strategist_llm", AsyncMock(side_effect=Exception("Model down"))):
        await strategist_node(state1, db_session=db_session)

    # Verify initial active strategy
    active1 = get_active_strategy_entries(db_session, creator.id)
    assert len(active1) == 1
    assert active1[0].value_json["finding"] == "Case studies have 2x shares"

    # Run 2: New finding for the same key
    run2 = create_run(db_session, run_type="goal", goal_id=goal.id)
    state2: ContentState = {
        "run_id": run2.id,
        "run_type": "goal",
        "depth_level": "standard",
        "user_goal": "Channel growth round 2",
        "creator_profile": {"creator_id": creator.id, "niche": "Cloud Engineering"},
        "analyst_findings": [
            {
                "finding": "Deep-dive architectural breakdowns exceed case studies by 50%",
                "recommendation": "Shift focus from basic case studies to system architectures",
                "confidence": "high",
                "sample_size": 14,
            }
        ],
    }

    with patch("app.agents.strategist.request_strategist_llm", AsyncMock(side_effect=Exception("Model down"))):
        await strategist_node(state2, db_session=db_session)

    # Active should have updated entry
    active2 = get_active_strategy_entries(db_session, creator.id)
    assert len(active2) == 1
    assert "Deep-dive architectural breakdowns" in active2[0].value_json["finding"]

    # History should contain both (old superseded, new active)
    history = get_strategy_history(db_session, creator.id, key="post_mortem_1")
    assert len(history) == 2
    statuses = [h.status for h in history]
    assert "active" in statuses
    assert "superseded" in statuses


@pytest.mark.asyncio
async def test_end_to_end_analyst_to_strategist_graph_flow(db_session: Session) -> None:
    """GRAPH-10 & IT-08: Complete graph execution from Analyst through Strategist."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Post-mortem analysis on videos")
    run = create_run(db_session, run_type="post_mortem", goal_id=goal.id)

    draft = create_draft_version(
        db_session,
        lineage_id="lin-e2e-1",
        version=1,
        kind="script",
        platform="youtube",
        content="E2E test script",
    )
    update_draft_status(db_session, draft.id, "POSTED")
    draft.posted_ref = "url"
    draft.posted_url = "https://youtube.com/watch?v=e2etestvid1"
    draft.posted_platform_id = "e2etestvid1"
    db_session.commit()

    create_performance_metric(db_session, draft.id, "youtube", "views", 5000.0)

    # Build compiled graph with db_session
    _ = create_content_graph(db_session=db_session)

    initial_state: ContentState = {
        "run_id": run.id,
        "run_type": "post_mortem",
        "depth_level": "quick",
        "user_goal": "Post-mortem analysis on videos",
        "creator_profile": {"creator_id": creator.id, "niche": "Web Dev"},
        "has_new_posts": True,
        "new_posts_count": 1,
        "tokens_used": 0,
        "execution_steps": 0,
    }

    with (
        patch("app.agents.analyst.request_analyst_llm", AsyncMock(side_effect=Exception("Model off"))),
        patch("app.agents.strategist.request_strategist_llm", AsyncMock(side_effect=Exception("Model off"))),
    ):
        # 1. Analyst node
        analyst_out = await analyst_node(initial_state, db_session=db_session)
        assert len(analyst_out["analyst_findings"]) >= 1

        # 2. Merge into state
        initial_state.update(analyst_out)  # type: ignore[typeddict-item]

        # 3. Supervisor decides next action
        eligible = calculate_eligible_nodes(initial_state)
        assert eligible == ["strategist"]

        # 4. Strategist node consumes findings
        strategist_out = await strategist_node(initial_state, db_session=db_session)
        assert strategist_out["approval_status"] == "PENDING"
        assert strategist_out["current_plan_id"] is not None

        # Verify strategy changes stored in database
        entries = get_active_strategy_entries(db_session, creator.id)
        assert len(entries) >= 1
