import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.repositories import (
    clear_creator_channel,
    create_approval,
    create_comment,
    create_comment_insight,
    create_draft_version,
    create_goal,
    create_plan_version,
    create_routing_log,
    create_run,
    create_task,
    decide_approval,
    delete_setting,
    get_all_settings,
    get_current_insights_for_channel,
    get_latest_draft_version,
    get_latest_plan_version,
    get_or_create_creator,
    get_run_tasks,
    get_setting,
    get_unprocessed_comments,
    mark_comments_processed,
    record_run_event,
    set_setting,
    update_creator_channel,
    update_run_status,
    update_task_status,
    upsert_content_item,
)


@pytest.fixture
def db_session() -> Session:
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(test_engine)


def test_creator_and_settings_repository(db_session: Session) -> None:
    # Test creator creation and updates
    creator = get_or_create_creator(db_session)
    assert creator.id is not None
    assert creator.display_name == "Creator"

    updated = update_creator_channel(
        db_session,
        channel_id="UC_test123",
        channel_handle="@testchannel",
        channel_title="Test Title",
        verified=True,
    )
    assert updated.youtube_channel_handle == "@testchannel"
    assert updated.youtube_channel_verified is True

    cleared = clear_creator_channel(db_session)
    assert cleared.youtube_channel_id is None
    assert cleared.youtube_channel_verified is False

    # Test settings repo
    set_setting(db_session, "default_depth_level", "standard")
    set_setting(db_session, "niche", "Python Engineering")
    assert get_setting(db_session, "default_depth_level") == "standard"
    assert get_setting(db_session, "niche") == "Python Engineering"

    all_settings = get_all_settings(db_session)
    assert len(all_settings) == 2

    assert delete_setting(db_session, "niche") is True
    assert get_setting(db_session, "niche") is None


def test_runs_and_tasks_repository(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Create 3 tutorial videos")
    assert goal.id is not None

    run = create_run(db_session, run_type="goal", depth_level="standard", goal_id=goal.id)
    assert run.status == "PENDING"

    run_updated = update_run_status(db_session, run.id, "RUNNING")
    assert run_updated is not None
    assert run_updated.status == "RUNNING"
    assert run_updated.started_at is not None

    task1 = create_task(db_session, run.id, "Analyze audience", "listener", 1)
    task2 = create_task(db_session, run.id, "Formulate plan", "strategist", 2)
    assert task2.id is not None
    tasks = get_run_tasks(db_session, run.id)
    assert len(tasks) == 2
    assert tasks[0].position == 1

    updated_task = update_task_status(db_session, task1.id, "DONE")
    assert updated_task is not None
    assert updated_task.status == "DONE"

    log = create_routing_log(
        db_session,
        run_id=run.id,
        step_number=1,
        from_node="supervisor",
        to_node="listener",
        reason="Initial comment analysis needed",
        decided_by="model",
        eligible_nodes=["listener", "research"],
        output_status="valid",
    )
    assert log.step_number == 1

    event = record_run_event(
        db_session,
        run_id=run.id,
        event_type="note",
        payload={"message": "Step 1 started"},
    )
    assert event.event_type == "note"


def test_content_and_comments_repository(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)
    item = upsert_content_item(
        db_session,
        creator_id=creator.id,
        platform="youtube",
        external_id="vid_999",
        owner_type="own",
        channel_external_id="UC_test123",
        title="Intro to Fastapi",
    )
    assert item.id is not None

    cmt1 = create_comment(db_session, item.id, "c_1", "How do I deploy this?")
    cmt2 = create_comment(db_session, item.id, "c_2", "Can you cover docker?")

    unprocessed = get_unprocessed_comments(db_session, [item.id])
    assert len(unprocessed) == 2

    processed_count = mark_comments_processed(db_session, [cmt1.id, cmt2.id])
    assert processed_count == 2
    assert len(get_unprocessed_comments(db_session, [item.id])) == 0

    run = create_run(db_session)
    insight = create_comment_insight(
        db_session,
        creator_id=creator.id,
        run_id=run.id,
        theme_label="Deployment Questions",
        comment_count=2,
        coverage_analyzed=2,
        coverage_total=2,
        source_item_ids=[item.id],
        example_comment_ids=[cmt1.id, cmt2.id],
    )
    assert insight.id is not None

    # ADR-032 Channel rule verification:
    # Own content of current channel matches
    matching = get_current_insights_for_channel(db_session, "UC_test123")
    assert len(matching) == 1
    # Different channel returns empty
    non_matching = get_current_insights_for_channel(db_session, "UC_other_channel")
    assert len(non_matching) == 0


def test_plans_drafts_and_approvals_repository(db_session: Session) -> None:
    run = create_run(db_session)
    items_data = [
        {
            "item_key": "item_k1",
            "topic": "FastAPI Deployment",
            "format": "video",
            "platform": "youtube",
            "objective": "Teach docker multi-stage build",
            "reason": "Top comment request",
            "priority": 1,
        }
    ]

    plan_v1 = create_plan_version(
        db_session,
        lineage_id="lin_p1",
        version=1,
        run_id=run.id,
        items=items_data,
        status="DRAFT",
    )
    assert plan_v1.version == 1
    assert len(plan_v1.items) == 1

    plan_v2 = create_plan_version(
        db_session,
        lineage_id="lin_p1",
        version=2,
        previous_version_id=plan_v1.id,
        run_id=run.id,
        items=items_data,
        status="PENDING_APPROVAL",
    )
    assert plan_v2.id is not None
    latest_plan = get_latest_plan_version(db_session, "lin_p1")
    assert latest_plan is not None
    assert latest_plan.version == 2

    # Draft versioning
    draft_v1 = create_draft_version(
        db_session,
        lineage_id="lin_d1",
        version=1,
        kind="script",
        platform="youtube",
        content="Draft 1 content",
    )
    assert draft_v1.version == 1

    draft_v2 = create_draft_version(
        db_session,
        lineage_id="lin_d1",
        version=2,
        previous_version_id=draft_v1.id,
        kind="script",
        platform="youtube",
        content="Draft 2 revised content",
        status="PENDING_APPROVAL",
    )
    latest_draft = get_latest_draft_version(db_session, "lin_d1")
    assert latest_draft is not None
    assert latest_draft.version == 2

    # Approvals
    approval = create_approval(db_session, item_type="draft", item_id=draft_v2.id, run_id=run.id)
    assert approval.status == "PENDING"

    decided = decide_approval(db_session, approval.id, decision="APPROVED")
    assert decided is not None
    assert decided.status == "DECIDED"
    assert decided.decision == "APPROVED"
    assert decided.decided_at is not None
