from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import RoutingLog
from app.db.repositories.runs import create_run, get_run_tasks
from app.graph import (
    ContentState,
    calculate_eligible_nodes,
    get_deterministic_default_node,
    supervisor_node,
)
from app.graph.supervisor import apply_task_updates, decompose_goal_to_tasks


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_ut01_eligible_nodes_scenarios() -> None:
    # 1. No audience data or research
    state_no_data: ContentState = {
        "comment_insights": [],
        "research_results": {},
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    assert calculate_eligible_nodes(state_no_data) == ["listener", "research"]

    # 2. Fresh insights exist, research missing
    state_insights_only: ContentState = {
        "comment_insights": [{"theme": "FastAPI"}],
        "research_results": {},
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    assert calculate_eligible_nodes(state_insights_only) == ["research", "strategist"]

    # 3. Plan waiting for human approval
    state_approval_waiting: ContentState = {
        "current_plan_id": "p1",
        "approval_status": "PENDING",
    }
    assert calculate_eligible_nodes(state_approval_waiting) == ["approval"]

    # 4. Plan was rejected with feedback
    state_plan_rejected: ContentState = {
        "current_plan_id": "p1",
        "approval_status": "REJECTED",
        "user_feedback": "Needs practical examples",
    }
    assert calculate_eligible_nodes(state_plan_rejected) == ["strategist"]

    # 5. Approved plan item without a draft
    state_needs_draft: ContentState = {
        "approval_status": "APPROVED",
        "content_plan": [{"item_key": "k1", "topic": "FastAPI"}],
        "current_draft_id": None,
    }
    assert calculate_eligible_nodes(state_needs_draft) == ["writer"]

    # 6. Finished tasks
    state_finished: ContentState = {
        "approval_status": "APPROVED",
        "content_plan": [{"item_key": "k1"}],
        "current_draft_id": "d1",
        "task_list": [{"id": "t1", "status": "DONE"}],
    }
    assert calculate_eligible_nodes(state_finished) == ["END"]


def test_deterministic_default_node() -> None:
    state: ContentState = {}
    node, reason = get_deterministic_default_node(["listener", "research"], state)
    assert node == "listener"
    assert "highest-priority" in reason

    node2, _ = get_deterministic_default_node(["writer", "strategist"], state)
    assert node2 == "strategist"


@pytest.mark.asyncio
async def test_ut03_single_eligible_node_skips_model() -> None:
    """UT-03: When only one node is eligible, the model is not called."""
    state: ContentState = {
        "approval_status": "PENDING",
        "execution_steps": 1,
    }
    # When approval_status is PENDING, calculate_eligible_nodes returns only ['approval']
    with patch("app.graph.supervisor.request_supervisor_llm") as mock_llm:
        updates = await supervisor_node(state)
        # Verify model was NOT called
        mock_llm.assert_not_called()
        assert updates["next_action"] == "approval"
        assert updates["execution_steps"] == 2
        assert updates["degraded"] is False


@pytest.mark.asyncio
async def test_ut02_decision_validation_and_fallback(db_session: Session) -> None:
    """UT-02: Decision outside eligible list is rejected, retried once, and replaced by default fallback."""
    state: ContentState = {
        "run_id": "run_test_01",
        "comment_insights": [],
        "research_results": {},
        "current_plan_id": None,
        "approval_status": "NONE",
        "execution_steps": 0,
    }
    # Eligible nodes: ['listener', 'research']
    # Model returns invalid node 'writer'
    mock_bad_response = {
        "message": {
            "content": '{"next_node": "writer", "reason": "Drafting now", "task_updates": []}'
        },
        "prompt_eval_count": 100,
        "eval_count": 25,
    }

    with patch(
        "app.graph.supervisor.request_supervisor_llm",
        new=AsyncMock(return_value=(mock_bad_response, 0.5)),
    ) as mock_llm:
        updates = await supervisor_node(state, db_session=db_session)
        # Verify it retried once (total 2 calls)
        assert mock_llm.call_count == 2
        # Verify fallback was used
        assert updates["next_action"] in ["listener", "research"]
        assert updates["degraded"] is True
        assert "fallback" in updates["degraded_reason"]

        # Verify routing log was written to SQLite
        log = db_session.query(RoutingLog).filter_by(run_id="run_test_01").first()
        assert log is not None
        assert log.output_status == "fallback"
        assert log.invalid_category == "ineligible_node"


@pytest.mark.asyncio
async def test_supervisor_valid_model_decision(db_session: Session) -> None:
    state: ContentState = {
        "run_id": "run_test_02",
        "comment_insights": [],
        "research_results": {},
        "current_plan_id": None,
        "approval_status": "NONE",
        "execution_steps": 0,
    }
    mock_valid_response = {
        "message": {
            "content": '{"next_node": "listener", "reason": "Analyze audience comments first", "task_updates": [{"action": "add", "title": "Fetch audience comments", "agent": "listener", "position": 1, "status": "TODO"}]}'
        },
        "prompt_eval_count": 120,
        "eval_count": 35,
    }

    with patch(
        "app.graph.supervisor.request_supervisor_llm",
        new=AsyncMock(return_value=(mock_valid_response, 0.4)),
    ):
        updates = await supervisor_node(state, db_session=db_session)
        assert updates["next_action"] == "listener"
        assert updates["degraded"] is False
        assert len(updates["task_list"]) == 1
        assert updates["task_list"][0]["title"] == "Fetch audience comments"

        log = db_session.query(RoutingLog).filter_by(run_id="run_test_02").first()
        assert log is not None
        assert log.output_status == "valid"
        assert log.to_node == "listener"


@pytest.mark.asyncio
async def test_ut04_step_budget_enforcement(db_session: Session) -> None:
    """UT-04: The run stops at the depth level's step limit with stop_reason set."""
    # Test for 'quick' depth level limit (15 steps)
    state_quick_at_limit: ContentState = {
        "run_id": "run_budget_quick",
        "depth_level": "quick",
        "execution_steps": 15,
        "next_action": "listener",
    }
    updates = await supervisor_node(state_quick_at_limit, db_session=db_session)
    assert updates["next_action"] == "END"
    assert updates["stop_reason"] == "step_budget_exceeded"
    assert updates["degraded"] is True
    assert "limit reached" in updates["degraded_reason"]

    # Verify routing log was written to SQLite
    log = db_session.query(RoutingLog).filter_by(run_id="run_budget_quick").first()
    assert log is not None
    assert log.to_node == "END"
    assert "limit reached" in log.reason

    # Test for 'standard' depth level limit (30 steps)
    state_standard_at_limit: ContentState = {
        "run_id": "run_budget_std",
        "depth_level": "standard",
        "execution_steps": 30,
        "next_action": "research",
    }
    updates_std = await supervisor_node(state_standard_at_limit, db_session=db_session)
    assert updates_std["next_action"] == "END"
    assert updates_std["stop_reason"] == "step_budget_exceeded"


@pytest.mark.asyncio
async def test_ut05_repeat_detection_consecutive(db_session: Session) -> None:
    """UT-05: Repeated routing between the same nodes is detected and stops."""
    # 3 consecutive identical nodes
    state_consecutive: ContentState = {
        "run_id": "run_repeat_01",
        "depth_level": "standard",
        "execution_steps": 5,
        "route_history": ["listener", "research", "research", "research"],
        "next_action": "research",
    }
    updates = await supervisor_node(state_consecutive, db_session=db_session)
    assert updates["next_action"] == "END"
    assert updates["stop_reason"] == "repeat_detected"
    assert updates["degraded"] is True
    assert "Consecutive routing repeat" in updates["degraded_reason"]


@pytest.mark.asyncio
async def test_ut05_repeat_detection_cycle(db_session: Session) -> None:
    """UT-05: 2-node ping-pong routing cycle is detected and stops."""
    state_cycle: ContentState = {
        "run_id": "run_repeat_02",
        "depth_level": "standard",
        "execution_steps": 6,
        "route_history": ["listener", "research", "listener", "research"],
        "next_action": "listener",
    }
    updates = await supervisor_node(state_cycle, db_session=db_session)
    assert updates["next_action"] == "END"
    assert updates["stop_reason"] == "repeat_detected"
    assert updates["degraded"] is True
    assert "ping-pong" in updates["degraded_reason"]


def test_at08_different_goals_produce_different_task_lists() -> None:
    """AT-08: Two different goals on the same creator produce different task lists."""
    # Goal 1: Script drafting focus
    goal_script = "Write a video script about FastAPI Middleware with benchmarks"
    tasks_script = decompose_goal_to_tasks(goal_script, depth_level="standard")

    # Goal 2: Repurposing focus
    goal_repurpose = "Repurpose my latest video into a LinkedIn post and X thread"
    tasks_repurpose = decompose_goal_to_tasks(goal_repurpose, depth_level="standard")

    # Goal 3: Performance analysis focus
    goal_analytics = "Analyze performance metrics and audience retention of recent uploads"
    tasks_analytics = decompose_goal_to_tasks(goal_analytics, depth_level="standard")

    # Verify task lists are distinct
    agents_script = [t["agent"] for t in tasks_script]
    agents_repurpose = [t["agent"] for t in tasks_repurpose]
    agents_analytics = [t["agent"] for t in tasks_analytics]

    assert agents_script != agents_repurpose
    assert agents_script != agents_analytics
    assert agents_repurpose != agents_analytics

    # Script drafting includes writer and critic
    assert "writer" in agents_script
    assert "critic" in agents_script

    # Analytics focuses on analyst and strategist
    assert "analyst" in agents_analytics
    assert "writer" not in agents_analytics

    # Verify positions are sequential 1..N
    for task_list in (tasks_script, tasks_repurpose, tasks_analytics):
        positions = [t["position"] for t in task_list]
        assert positions == list(range(1, len(task_list) + 1))


def test_apply_task_updates_progression_and_replanning() -> None:
    """Tests automatic task completion, dynamic replanning on rejection, and update actions."""
    initial_tasks = [
        {"id": "t1", "title": "Listen to comments", "agent": "listener", "position": 1, "status": "TODO"},
        {"id": "t2", "title": "Research competitors", "agent": "research", "position": 2, "status": "TODO"},
        {"id": "t3", "title": "Create plan", "agent": "strategist", "position": 3, "status": "TODO"},
    ]

    # 1. Returning from listener marks t1 as DONE
    step1_tasks = apply_task_updates(initial_tasks, [], from_node="listener")
    assert step1_tasks[0]["status"] == "DONE"
    assert step1_tasks[1]["status"] == "TODO"

    # 2. Returning from strategist marks t3 as DONE
    step2_tasks = apply_task_updates(step1_tasks, [], from_node="strategist")
    assert step2_tasks[2]["status"] == "DONE"

    # 3. Resumed run never repeats or deletes a DONE task
    # Attempting to remove t1 should be ignored
    step3_tasks = apply_task_updates(step2_tasks, [{"action": "remove", "task_id": "t1"}])
    assert any(t["id"] == "t1" and t["status"] == "DONE" for t in step3_tasks)

    # 4. Dynamic replanning when plan is rejected
    step4_tasks = apply_task_updates(step3_tasks, [], from_node="approval", approval_status="REJECTED")
    revision_task = next(
        (t for t in step4_tasks if "Revise content plan" in t["title"]), None
    )
    assert revision_task is not None
    assert revision_task["agent"] == "strategist"
    assert revision_task["status"] == "TODO"

    # 5. Reordering tasks preserves normalized sequential positions
    reordered = apply_task_updates(
        step4_tasks,
        [{"action": "reorder", "task_id": "t2", "position": 10}],
    )
    positions = [t["position"] for t in reordered]
    assert positions == list(range(1, len(reordered) + 1))


@pytest.mark.asyncio
async def test_supervisor_initializes_tasks_and_persists_to_db(db_session: Session) -> None:
    """Verifies that an uninitialized run decomposes goal and persists tasks in SQLite."""
    run = create_run(db_session, run_type="goal", depth_level="standard")
    state: ContentState = {
        "run_id": run.id,
        "user_goal": "Write a script tutorial on Python asyncio",
        "depth_level": "standard",
        "task_list": [],
        "execution_steps": 0,
        "comment_insights": [],
        "research_results": {},
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    mock_response = {
        "message": {
            "content": '{"next_node": "research", "reason": "Research background first", "task_updates": []}'
        },
        "prompt_eval_count": 100,
        "eval_count": 20,
    }

    with patch(
        "app.graph.supervisor.request_supervisor_llm",
        new=AsyncMock(return_value=(mock_response, 0.1)),
    ):
        updates = await supervisor_node(state, db_session=db_session)
        assert len(updates["task_list"]) > 0

        # Verify persisted in database
        db_tasks = get_run_tasks(db_session, run.id)
        assert len(db_tasks) == len(updates["task_list"])
        assert all(t.run_id == run.id for t in db_tasks)
        assert db_tasks[0].position == 1


def test_at06_stale_research_is_repeated_fresh_research_is_not() -> None:
    """AT-06 / GRAPH-07: Stale research is repeated. Fresh research is not."""
    # Case 1: Fresh research results exist along with comment insights
    state_fresh_research: ContentState = {
        "comment_insights": [{"theme": "FastAPI"}],
        "research_results": {"topics": ["AsyncIO", "Pydantic"]},
        "research_is_stale": False,
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible_fresh = calculate_eligible_nodes(state_fresh_research)
    # Research is fresh, so research is skipped and strategist is eligible directly
    assert eligible_fresh == ["strategist"]
    assert "research" not in eligible_fresh

    # Case 2: Research results exist but are marked stale
    state_stale_research: ContentState = {
        "comment_insights": [{"theme": "FastAPI"}],
        "research_results": {"topics": ["Old 2024 benchmarks"]},
        "research_is_stale": True,
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible_stale = calculate_eligible_nodes(state_stale_research)
    # Stale research must be repeated
    assert "research" in eligible_stale


def test_at05_thin_data_triggers_research_repeat() -> None:
    """AT-05 / GRAPH-07: Thin data triggers research repetition to gather evidence."""
    state_thin_data: ContentState = {
        "comment_insights": [{"theme": "FastAPI"}],
        "research_results": {"topics": ["Single item"]},
        "data_is_thin": True,
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible = calculate_eligible_nodes(state_thin_data)
    assert eligible == ["research"]


def test_at07_brief_with_no_new_posts_skips_analyst() -> None:
    """AT-07 / GRAPH-07: Brief with no new posts skips the Analyst."""
    # Weekly Brief with no new posts
    state_no_posts: ContentState = {
        "run_type": "weekly_brief",
        "has_new_posts": False,
        "new_posts_count": 0,
        "comment_insights": [{"theme": "FastAPI"}],
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible_no_posts = calculate_eligible_nodes(state_no_posts)
    assert "analyst" not in eligible_no_posts

    # Weekly Brief with new posts available
    state_with_posts: ContentState = {
        "run_type": "weekly_brief",
        "has_new_posts": True,
        "new_posts_count": 3,
        "comment_insights": [{"theme": "FastAPI"}],
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible_with_posts = calculate_eligible_nodes(state_with_posts)
    assert "analyst" in eligible_with_posts


def test_apply_task_updates_skip_and_repeat_transitions() -> None:
    """Tests task status transitions: skipping fresh listener/analyst, repeating stale research."""
    initial_tasks = [
        {"id": "t1", "title": "Analyze comments", "agent": "listener", "position": 1, "status": "TODO"},
        {"id": "t2", "title": "Research competitors", "agent": "research", "position": 2, "status": "DONE"},
        {"id": "t3", "title": "Post-mortem analysis", "agent": "analyst", "position": 3, "status": "TODO"},
    ]

    # State has fresh comments and no new posts, but research is stale
    state: ContentState = {
        "comment_insights": [{"theme": "Async"}],
        "insights_is_stale": False,
        "research_is_stale": True,
        "has_new_posts": False,
    }

    updated = apply_task_updates(initial_tasks, [], state=state)

    # 1. Listener is SKIPPED because comments are already fresh
    assert updated[0]["agent"] == "listener"
    assert updated[0]["status"] == "SKIPPED"

    # 2. Analyst is SKIPPED because there are no new posts
    analyst_task = next(t for t in updated if t["agent"] == "analyst")
    assert analyst_task["status"] == "SKIPPED"

    # 3. New research task is appended to repeat research because it was stale
    repeat_research_task = next(
        t for t in updated if "Repeat research" in t["title"]
    )
    assert repeat_research_task is not None
    assert repeat_research_task["status"] == "TODO"
