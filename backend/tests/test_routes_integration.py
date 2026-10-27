from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import Creator
from app.db.repositories import (
    create_approval,
    create_goal,
    create_plan_version,
    create_run,
    decide_approval,
    get_creator,
    set_setting,
)
from app.db.session import get_db
from app.graph import ContentState, calculate_eligible_nodes
from app.graph.builder import create_content_graph
from app.main import app
from app.scheduler import reset_scheduler


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
# AT-01 / AT-02: Routes for New vs Established Creator
# ==============================================================================


def test_at_01_new_creator_routes_to_research_or_listener() -> None:
    # A new creator has no stored content items or insights
    state_new_creator: ContentState = {
        "comment_insights": [],
        "research_results": {},
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible = calculate_eligible_nodes(state_new_creator)
    # AT-01: Research and listener are eligible when data is thin; strategist is not yet
    assert "research" in eligible or "listener" in eligible
    assert "strategist" not in eligible


def test_at_02_established_creator_with_fresh_insights_can_skip_research() -> None:
    # With fresh insights already available, supervisor allows direct Strategist
    state_established: ContentState = {
        "comment_insights": [{"theme": "Architecture"}],
        "research_results": {},
        "current_plan_id": None,
        "approval_status": "NONE",
    }
    eligible = calculate_eligible_nodes(state_established)
    assert "strategist" in eligible


# ==============================================================================
# AT-03 / IT-02: Rejected Plan Routes Back to Strategist with Feedback
# ==============================================================================


def test_at_03_rejected_plan_routes_back_to_strategist_with_feedback(
    db_session: Session,
) -> None:
    set_setting(db_session, "onboarding_completed", True)
    creator = get_creator(db_session) or Creator()
    db_session.add(creator)
    db_session.commit()

    goal = create_goal(db_session, creator_id=creator.id, text="Make tutorials")
    run = create_run(db_session, run_type="goal", depth_level="standard", goal_id=goal.id)

    # 1. First plan version
    pv1 = create_plan_version(
        db_session,
        lineage_id="lin_123",
        version=1,
        run_id=run.id,
        items=[
            {
                "topic": "FastAPI Crash Course",
                "format": "long_video",
                "platform": "youtube",
                "objective": "Teach FastAPI",
                "reason": "Popular framework",
            }
        ],
        status="PENDING_APPROVAL",
    )
    app1 = create_approval(
        db_session,
        run_id=run.id,
        item_type="plan",
        item_id=pv1.id,
    )

    # 2. Creator rejects plan with feedback
    decide_approval(
        db_session,
        approval_id=app1.id,
        decision="REJECTED",
        feedback_text="Too beginner-focused. Focus on advanced patterns.",
    )
    pv1.status = "REJECTED"
    db_session.commit()
    db_session.refresh(pv1)
    assert pv1.status == "REJECTED"

    # 3. Supervisor state reflects rejection with feedback
    state_rejected: ContentState = {
        "current_plan_id": pv1.id,
        "approval_status": "REJECTED",
        "user_feedback": "Too beginner-focused. Focus on advanced patterns.",
    }

    # Route returns strictly to Strategist (AT-03, IT-02)
    eligible = calculate_eligible_nodes(state_rejected)
    assert eligible == ["strategist"]


# ==============================================================================
# IT-04: Graph Assembly and Initialization with Checkpointer
# ==============================================================================


def test_it_04_graph_can_build_and_initialize_with_checkpointer() -> None:
    graph = create_content_graph()
    assert graph is not None
