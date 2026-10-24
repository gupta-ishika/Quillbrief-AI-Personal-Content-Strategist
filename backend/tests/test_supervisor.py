from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import RoutingLog
from app.graph import (
    ContentState,
    calculate_eligible_nodes,
    get_deterministic_default_node,
    supervisor_node,
)


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
