import tempfile
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Approval, ContentPlan, Run
from app.db.repositories.plans import create_plan_version
from app.graph.approval import (
    StaleApprovalError,
    approval_node,
    resume_paused_run,
)
from app.graph.state import ContentState
from app.schemas.approvals import ApprovalDecisionRequest
from app.tools.approval_tool import approval_tool_func


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


def build_test_approval_graph(checkpointer: Any, db: Session) -> Any:
    """Builds a test graph with approval node using the provided checkpointer."""
    workflow = StateGraph(ContentState)

    def bound_approval_node(state: ContentState) -> dict[str, Any]:
        return approval_node(state, db_session=db)

    workflow.add_node("approval", bound_approval_node)
    workflow.add_edge(START, "approval")
    workflow.add_edge("approval", END)

    return workflow.compile(checkpointer=checkpointer)


def test_approval_tool_inspection(db_session: Session) -> None:
    """HITL-01 / UT-32: approval_tool inspects approval state."""
    app = Approval(
        id="app_tool_01",
        run_id="run_01",
        item_type="plan",
        item_id="plan_01",
        status="PENDING",
    )
    db_session.add(app)
    db_session.commit()

    with patch_session(db_session):
        res = approval_tool_func(item_id="plan_01")
        assert res["status"] == "PENDING"
        assert res["item_id"] == "plan_01"
        assert res["verified"] is True


def patch_session(db: Session):
    from unittest.mock import patch

    class FakeSessionContext:
        def __enter__(self):
            return db

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    return patch("app.tools.approval_tool.SessionLocal", return_value=FakeSessionContext())


def test_approval_node_pauses_and_approves(db_session: Session) -> None:
    """HITL-01: Graph pauses at approval_node and resumes on APPROVED decision."""
    # Seed plan & run
    run = Run(id="run_hitl_01", run_type="goal", status="RUNNING")
    db_session.add(run)
    db_session.commit()

    plan = create_plan_version(
        db=db_session,
        lineage_id="lin_01",
        version=1,
        run_id="run_hitl_01",
        items=[
            {
                "topic": "FastAPI Testing",
                "format": "video",
                "platform": "youtube",
                "objective": "Guide",
                "reason": "Popular",
                "source_type": "own_idea",
            }
        ],
        status="PENDING_APPROVAL",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "checkpoints.db")
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            graph = build_test_approval_graph(checkpointer=checkpointer, db=db_session)
            config = {"configurable": {"thread_id": "run_hitl_01"}}

            initial_state: ContentState = {
                "run_id": "run_hitl_01",
                "current_plan_id": plan.id,
                "current_plan_version": 1,
                "approval_item_id": plan.id,
                "approval_item_type": "plan",
                "approval_status": "NONE",
            }

            # 1. First execution: should pause at interrupt
            graph.invoke(initial_state, config=config)

            # Execution is interrupted: check interrupt in state
            state_snapshot = graph.get_state(config)
            assert len(state_snapshot.tasks) > 0
            assert state_snapshot.tasks[0].interrupts

            # Verify Approval row was created in SQLite with PENDING status
            app_row = db_session.query(Approval).filter_by(item_id=plan.id).first()
            assert app_row is not None
            assert app_row.status == "PENDING"

            # Verify Run status was set to WAITING_APPROVAL
            db_session.refresh(run)
            assert run.status == "WAITING_APPROVAL"

            # 2. Resume execution with APPROVED decision
            resume_decision = {"decision": "APPROVED"}
            resumed_result = graph.invoke(Command(resume=resume_decision), config=config)

            assert resumed_result["approval_status"] == "APPROVED"
            assert resumed_result["next_action"] == "supervisor"

            # Verify database updates
            db_session.refresh(app_row)
            assert app_row.status == "DECIDED"
            assert app_row.decision == "APPROVED"
            assert app_row.decided_at is not None

            db_session.refresh(plan)
            assert plan.status == "APPROVED"
            assert plan.approved_at is not None

            db_session.refresh(run)
            assert run.status == "RUNNING"


def test_approval_node_rejects_with_feedback(db_session: Session) -> None:
    """HITL-01 / FR-4: Graph pauses and handles REJECTED decision with feedback."""
    run = Run(id="run_hitl_02", run_type="goal", status="RUNNING")
    db_session.add(run)
    db_session.commit()

    plan = create_plan_version(
        db=db_session,
        lineage_id="lin_02",
        version=1,
        run_id="run_hitl_02",
        items=[
            {
                "topic": "Basic Intro",
                "format": "video",
                "platform": "youtube",
                "objective": "Intro",
                "reason": "Basics",
                "source_type": "own_idea",
            }
        ],
        status="PENDING_APPROVAL",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "checkpoints.db")
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            graph = build_test_approval_graph(checkpointer=checkpointer, db=db_session)
            config = {"configurable": {"thread_id": "run_hitl_02"}}

            initial_state: ContentState = {
                "run_id": "run_hitl_02",
                "current_plan_id": plan.id,
                "current_plan_version": 1,
                "approval_item_id": plan.id,
                "approval_item_type": "plan",
                "approval_status": "NONE",
            }

            graph.invoke(initial_state, config=config)

            # Resume with REJECTED and feedback
            resume_decision = {
                "decision": "REJECTED",
                "feedback_text": "Need more advanced production scenarios.",
            }
            resumed_result = graph.invoke(Command(resume=resume_decision), config=config)

            assert resumed_result["approval_status"] == "REJECTED"
            assert resumed_result["user_feedback"] == "Need more advanced production scenarios."

            app_row = db_session.query(Approval).filter_by(item_id=plan.id).first()
            assert app_row is not None
            assert app_row.status == "DECIDED"
            assert app_row.decision == "REJECTED"
            assert app_row.feedback_text == "Need more advanced production scenarios."

            db_session.refresh(plan)
            assert plan.status == "REJECTED"


def test_approval_node_edited_creates_approved_version(db_session: Session) -> None:
    """ADR-029 / UT-22: EDITED decision supersedes old plan and creates approved creator version."""
    run = Run(id="run_hitl_03", run_type="goal", status="RUNNING")
    db_session.add(run)
    db_session.commit()

    plan = create_plan_version(
        db=db_session,
        lineage_id="lin_03",
        version=1,
        run_id="run_hitl_03",
        items=[
            {
                "topic": "Original Topic",
                "format": "video",
                "platform": "youtube",
                "objective": "Original",
                "reason": "Test",
                "source_type": "own_idea",
            }
        ],
        status="PENDING_APPROVAL",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "checkpoints.db")
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            graph = build_test_approval_graph(checkpointer=checkpointer, db=db_session)
            config = {"configurable": {"thread_id": "run_hitl_03"}}

            initial_state: ContentState = {
                "run_id": "run_hitl_03",
                "current_plan_id": plan.id,
                "current_plan_version": 1,
                "approval_item_id": plan.id,
                "approval_item_type": "plan",
                "approval_status": "NONE",
            }

            graph.invoke(initial_state, config=config)

            # Creator edits the content directly
            edited_items = [
                {
                    "topic": "Creator Custom Architecture Guide",
                    "format": "video",
                    "platform": "youtube",
                    "objective": "Creator Edited",
                    "reason": "Customized by creator during review",
                    "source_type": "own_idea",
                }
            ]

            resume_decision = {
                "decision": "EDITED",
                "edited_content": edited_items,
                "feedback_text": "Tweaked topic title and objective",
            }

            resumed_result = graph.invoke(Command(resume=resume_decision), config=config)

            assert resumed_result["approval_status"] == "EDITED"
            assert resumed_result["current_plan_version"] == 2
            assert resumed_result["current_plan_id"] != plan.id

            # Verify old plan superseded
            db_session.refresh(plan)
            assert plan.status == "SUPERSEDED"

            # Verify new creator plan created and approved
            new_plan = (
                db_session.query(ContentPlan)
                .filter_by(id=resumed_result["current_plan_id"])
                .first()
            )
            assert new_plan is not None
            assert new_plan.version == 2
            assert new_plan.created_by == "creator"
            assert new_plan.status == "APPROVED"
            assert new_plan.previous_version_id == plan.id
            assert len(new_plan.items) == 1
            assert new_plan.items[0].topic == "Creator Custom Architecture Guide"


def test_hitl02_resume_paused_run_after_backend_restart(db_session: Session) -> None:
    """HITL-02: Paused run persists in SQLite checkpoints and resumes cleanly after process restart."""
    run = Run(id="run_restart_01", run_type="goal", status="RUNNING")
    db_session.add(run)
    db_session.commit()

    plan = create_plan_version(
        db=db_session,
        lineage_id="lin_restart",
        version=1,
        run_id="run_restart_01",
        items=[
            {
                "topic": "Restart Resilience",
                "format": "video",
                "platform": "youtube",
                "objective": "Resilience",
                "reason": "Reliability",
                "source_type": "own_idea",
            }
        ],
        status="PENDING_APPROVAL",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "checkpoints.db")

        # Session 1: Run graph until interrupt, then close / restart
        with SqliteSaver.from_conn_string(db_path) as checkpointer1:
            graph1 = build_test_approval_graph(checkpointer=checkpointer1, db=db_session)
            config = {"configurable": {"thread_id": "run_restart_01"}}

            initial_state: ContentState = {
                "run_id": "run_restart_01",
                "current_plan_id": plan.id,
                "current_plan_version": 1,
                "approval_item_id": plan.id,
                "approval_item_type": "plan",
                "approval_status": "NONE",
            }

            graph1.invoke(initial_state, config=config)

        # Process restart simulation: graph1 and checkpointer1 destroyed.
        # Session 2: Fresh graph and fresh checkpointer connecting to same SQLite db file.
        with SqliteSaver.from_conn_string(db_path) as checkpointer2:
            graph2 = build_test_approval_graph(checkpointer=checkpointer2, db=db_session)
            config = {"configurable": {"thread_id": "run_restart_01"}}

            # Verify checkpoint preserved the interrupted state across process restart
            saved_state = graph2.get_state(config)
            assert len(saved_state.tasks) > 0
            assert saved_state.tasks[0].interrupts
            assert saved_state.values["approval_item_id"] == plan.id

            # Resume using resume_paused_run helper
            req = ApprovalDecisionRequest(
                item_id=plan.id,
                decision="APPROVED",
            )
            resumed_output = resume_paused_run(
                graph=graph2,
                run_id="run_restart_01",
                decision_request=req,
                db=db_session,
            )

            assert resumed_output["approval_status"] == "APPROVED"
            assert resumed_output["current_plan_id"] == plan.id

            db_session.refresh(plan)
            assert plan.status == "APPROVED"


def test_stale_approval_rejected(db_session: Session) -> None:
    """UT-20: Submitting approval for mismatched or non-pending item raises StaleApprovalError."""
    # Approval already DECIDED
    app = Approval(
        id="app_decided",
        run_id="run_stale_01",
        item_type="plan",
        item_id="plan_stale_01",
        status="DECIDED",
        decision="APPROVED",
    )
    db_session.add(app)
    db_session.commit()

    req = ApprovalDecisionRequest(
        item_id="plan_stale_01",
        decision="APPROVED",
    )

    with pytest.raises(StaleApprovalError, match="No pending approval found"):
        resume_paused_run(
            graph=None,
            run_id="run_stale_01",
            decision_request=req,
            db=db_session,
        )
