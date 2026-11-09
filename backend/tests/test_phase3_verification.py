import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.approvals import decide_approval_endpoint, get_approval_by_id
from app.db.base import Base
from app.db.models import Approval, RunEvent
from app.db.repositories.runs import (
    create_run,
    sync_run_tasks,
)
from app.graph import (
    ContentState,
    calculate_eligible_nodes,
    supervisor_node,
)
from app.graph.supervisor import apply_task_updates, decompose_goal_to_tasks
from app.schemas.approvals import ApprovalDecisionRequest


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


def test_at08_goal_decomposition_distinct_task_lists() -> None:
    """AT-08: Two different goals produce different task lists."""
    goal_video = "Write a YouTube video script on FastAPI performance"
    goal_repurpose = "Repurpose my latest video into a LinkedIn post and tweet thread"

    profile = {"niche": "Software Engineering"}

    tasks_video = decompose_goal_to_tasks(goal_video, "standard", profile)
    tasks_repurpose = decompose_goal_to_tasks(goal_repurpose, "standard", profile)

    agents_video = [t["agent"] for t in tasks_video]
    agents_repurpose = [t["agent"] for t in tasks_repurpose]

    # Video creation involves listening, research, strategy, writing, critic review, and approval
    assert "writer" in agents_video
    assert "critic" in agents_video
    assert "repurposer" not in agents_video

    # Repurposing involves repurposer agent and approval
    assert "repurposer" in agents_repurpose
    assert "writer" not in agents_repurpose

    # Positions must be strictly sequential 1..N
    assert [t["position"] for t in tasks_video] == list(range(1, len(tasks_video) + 1))
    assert [t["position"] for t in tasks_repurpose] == list(range(1, len(tasks_repurpose) + 1))


def test_at06_stale_research_repeated_fresh_research_skipped() -> None:
    """AT-06: Stale research is repeated; fresh research is not."""
    # 1. Stale research scenario: research must be eligible and repeated
    state_stale: ContentState = {
        "comment_insights": [{"theme": "Python"}],
        "research_results": {"opportunities": [{"topic": "Old"}], "is_stale": True},
        "research_is_stale": True,
        "insights_is_stale": False,
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible_stale = calculate_eligible_nodes(state_stale)
    assert eligible_stale == ["research"]

    initial_tasks = [
        {"id": "t1", "title": "Analyze audience", "agent": "listener", "position": 1, "status": "DONE"},
        {"id": "t2", "title": "Research competitors", "agent": "research", "position": 2, "status": "DONE"},
    ]
    updated_tasks = apply_task_updates(initial_tasks, [], state=state_stale)
    assert any("Repeat research" in t["title"] for t in updated_tasks)

    # 2. Fresh research scenario: both insights and research are fresh -> research skipped, strategist eligible
    state_fresh: ContentState = {
        "comment_insights": [{"theme": "Python"}],
        "research_results": {"opportunities": [{"topic": "Fresh"}], "is_stale": False},
        "research_is_stale": False,
        "insights_is_stale": False,
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible_fresh = calculate_eligible_nodes(state_fresh)
    assert eligible_fresh == ["strategist"]
    assert "research" not in eligible_fresh
    assert "listener" not in eligible_fresh


def test_at05_thin_data_triggers_repeat_or_depth_increase() -> None:
    """AT-05: Thin data triggers research repetition or depth increase proposal."""
    # When data is thin at quick depth:
    state_thin_quick: ContentState = {
        "depth_level": "quick",
        "comment_insights": [{"theme": "Async"}],
        "research_results": {"opportunities": []},
        "data_is_thin": True,
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible = calculate_eligible_nodes(state_thin_quick)
    # Both repeating research and proposing higher depth level are valid routes
    assert "research" in eligible
    assert "approval" in eligible


@pytest.mark.asyncio
async def test_it05_budget_stop_reports_unfinished_and_offers_depth_increase(
    db_session: Session,
) -> None:
    """IT-05: A run that hits its budget stops, reports what is unfinished, and offers a depth increase request."""
    run = create_run(db_session, run_type="goal", depth_level="quick")

    raw_tasks = [
        {"title": "Audience analysis", "agent": "listener", "position": 1, "status": "DONE"},
        {"title": "Competitor research", "agent": "research", "position": 2, "status": "DONE"},
        {"title": "Develop content plan", "agent": "strategist", "position": 3, "status": "TODO"},
        {"title": "Draft script", "agent": "writer", "position": 4, "status": "TODO"},
    ]
    db_tasks = sync_run_tasks(db_session, run.id, raw_tasks)

    task_dicts = [
        {"id": t.id, "title": t.title, "agent": t.agent, "position": t.position, "status": t.status}
        for t in db_tasks
    ]

    state_budget_exhausted: ContentState = {
        "run_id": run.id,
        "depth_level": "quick",  # quick supervisor limit is 15
        "execution_steps": 15,
        "task_list": task_dicts,
        "creator_profile": {"niche": "Tech Education"},
        "user_goal": "Scale technical audience",
    }

    # Supervisor handles step budget exhaustion
    result = await supervisor_node(state_budget_exhausted, db_session=db_session)

    # 1. Run stops with stop_reason set
    assert result["next_action"] == "END"
    assert result["stop_reason"] == "step_budget_exceeded"
    assert result["degraded"] is True

    # 2. Reports what is unfinished in degraded_reason
    assert "Develop content plan" in result["degraded_reason"]
    assert "Draft script" in result["degraded_reason"]

    # 3. limit_reached event is stored
    event = db_session.query(RunEvent).filter_by(run_id=run.id, event_type="limit_reached").first()
    assert event is not None
    assert event.payload_json["limit"] == "step_budget"
    assert "Develop content plan" in event.payload_json["unfinished_tasks"]

    # 4. Offers a depth increase request (PENDING approval record)
    depth_approval = (
        db_session.query(Approval)
        .filter_by(run_id=run.id, item_type="depth_increase", status="PENDING")
        .first()
    )
    assert depth_approval is not None
    assert depth_approval.item_id == run.id
    assert "Propose increasing depth to 'standard'" in depth_approval.feedback_text


def test_it06_depth_increase_approval_raises_limits_for_that_run_only(
    db_session: Session,
) -> None:
    """IT-06: Approving the depth increase raises limits for that run only."""
    # Create two runs: run_target at quick depth, run_other at quick depth
    run_target = create_run(db_session, run_type="goal", depth_level="quick")
    run_target.status = "STOPPED"
    run_target.stop_reason = "step_budget_exceeded"

    run_other = create_run(db_session, run_type="goal", depth_level="quick")

    db_session.commit()

    # Pending depth increase approval for run_target
    approval = Approval(
        run_id=run_target.id,
        item_type="depth_increase",
        item_id=run_target.id,
        status="PENDING",
        feedback_text="Step limit reached at quick depth. Propose increasing to standard.",
    )
    db_session.add(approval)
    db_session.commit()

    # Verify preview via GET
    app_resp = get_approval_by_id(approval.id, db=db_session)
    assert app_resp.item_type == "depth_increase"
    assert app_resp.item_details["current_depth"] == "quick"
    assert app_resp.item_details["proposed_depth"] == "standard"

    # Approve depth increase
    decide_req = ApprovalDecisionRequest(item_id=run_target.id, decision="APPROVED")
    decision_resp = decide_approval_endpoint(approval.id, decide_req, db=db_session)

    assert decision_resp.approval.decision == "APPROVED"
    assert decision_resp.resulting_item_id == run_target.id
    assert decision_resp.resumed_run_id == run_target.id

    # Refresh runs
    db_session.refresh(run_target)
    db_session.refresh(run_other)

    # 1. run_target limits are raised to 'standard'
    assert run_target.depth_level == "standard"
    assert run_target.status == "RUNNING"
    assert run_target.stop_reason is None

    # 2. run_other remains strictly at 'quick' (raised for that run only)
    assert run_other.depth_level == "quick"

    # 3. Note event recorded on run_target
    event = db_session.query(RunEvent).filter_by(run_id=run_target.id, event_type="note").first()
    assert event is not None
    assert "Depth level raised from 'quick' to 'standard'" in event.payload_json["message"]
