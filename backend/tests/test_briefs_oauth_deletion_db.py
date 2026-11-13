"""Database and repository tests for WeeklyBriefs, OAuthStates, and DeletionJobs (DB-05).

Validates:
- weekly_briefs table: scheduled period_key unique index, manual vs scheduled trigger, status checks, cascades
- oauth_states table: state_hash PK, platform & return_to check constraints, expiration and cleanup
- deletion_jobs table: status check constraint, steps_json, independence from creators table
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.repositories.briefs import (
    archive_weekly_brief,
    cleanup_expired_or_used_oauth_states,
    create_deletion_job,
    create_oauth_state,
    create_weekly_brief,
    get_deletion_job,
    get_latest_deletion_job,
    get_latest_weekly_brief,
    get_oauth_state,
    get_weekly_brief_by_period_key,
    list_weekly_briefs,
    mark_oauth_state_used,
    mark_weekly_brief_read,
    update_deletion_job,
)
from app.db.repositories.creator import get_or_create_creator
from app.db.repositories.plans import create_plan_version
from app.db.repositories.runs import create_goal, create_run


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
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
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_weekly_brief_scheduled_and_manual_triggers(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Goal for Weekly Brief")
    run1 = create_run(db_session, goal_id=goal.id, run_type="weekly_brief")
    run2 = create_run(db_session, goal_id=goal.id, run_type="weekly_brief")

    # 1. Scheduled brief with period_key
    brief1 = create_weekly_brief(
        db=db_session,
        run_id=run1.id,
        trigger="scheduled",
        period_key="2026-W46",
        content_markdown="# Weekly Strategic Brief (Week 46)\n- Key Trends",
    )
    assert brief1.id is not None
    assert brief1.trigger == "scheduled"
    assert brief1.period_key == "2026-W46"
    assert brief1.status == "GENERATED"
    assert brief1.read_at is None

    # Duplicate scheduled brief for SAME period_key must fail unique constraint
    with pytest.raises(IntegrityError):
        create_weekly_brief(
            db=db_session,
            run_id=run2.id,
            trigger="scheduled",
            period_key="2026-W46",
            content_markdown="# Duplicate Brief",
        )
    db_session.rollback()

    # 2. Manual brief with period_key=None succeeds
    manual1 = create_weekly_brief(
        db=db_session,
        run_id=run1.id,
        trigger="manual",
        content_markdown="# Manual On-Demand Brief",
    )
    assert manual1.period_key is None

    # Multiple manual briefs do NOT conflict
    manual2 = create_weekly_brief(
        db=db_session,
        run_id=run2.id,
        trigger="manual",
        content_markdown="# Another Manual Brief",
    )
    assert manual2.period_key is None


def test_weekly_brief_query_and_state_transitions(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Goal for Brief State Transitions")
    run = create_run(db_session, goal_id=goal.id, run_type="weekly_brief")

    plan = create_plan_version(
        db=db_session,
        lineage_id="lineage-bplan-1",
        version=1,
        run_id=run.id,
        items=[],
        created_by="strategist",
    )

    brief = create_weekly_brief(
        db=db_session,
        run_id=run.id,
        trigger="scheduled",
        period_key="2026-W47",
        content_markdown="# Content Strategy Brief",
        plan_id=plan.id,
    )

    # Lookup by period key
    found = get_weekly_brief_by_period_key(db_session, "2026-W47")
    assert found is not None
    assert found.id == brief.id
    assert found.plan_id == plan.id

    # Mark as read
    assert brief.read_at is None
    mark_weekly_brief_read(db_session, brief.id)
    db_session.refresh(brief)
    assert brief.read_at is not None

    # Archive brief
    archive_weekly_brief(db_session, brief.id)
    db_session.refresh(brief)
    assert brief.status == "ARCHIVED"

    # List briefs by status
    archived = list_weekly_briefs(db_session, status="ARCHIVED")
    assert len(archived) == 1
    assert archived[0].id == brief.id

    # Latest brief
    latest = get_latest_weekly_brief(db_session)
    assert latest is not None
    assert latest.id == brief.id


def test_weekly_brief_check_constraints(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Brief Constraints")
    run = create_run(db_session, goal_id=goal.id, run_type="weekly_brief")

    # Invalid trigger
    with pytest.raises(IntegrityError):
        create_weekly_brief(
            db=db_session,
            run_id=run.id,
            trigger="invalid_trigger",
            content_markdown="Content",
        )
    db_session.rollback()

    # Invalid status
    with pytest.raises(IntegrityError):
        create_weekly_brief(
            db=db_session,
            run_id=run.id,
            trigger="manual",
            content_markdown="Content",
            status="INVALID_STATUS",
        )
    db_session.rollback()


def test_oauth_states_lifecycle_and_cleanup(db_session: Session) -> None:
    now = datetime.now(UTC)

    # 1. Create valid state hash for settings return
    state_valid = create_oauth_state(
        db=db_session,
        state_hash="hash_valid_12345",
        platform="youtube",
        return_to="settings",
        expires_in_minutes=10,
    )
    assert state_valid.platform == "youtube"
    assert state_valid.return_to == "settings"
    assert state_valid.used_at is None
    expires_valid = (
        state_valid.expires_at.replace(tzinfo=UTC)
        if state_valid.expires_at.tzinfo is None
        else state_valid.expires_at
    )
    assert expires_valid > now

    # 2. Create state hash for onboarding return
    state_onboarding = create_oauth_state(
        db=db_session,
        state_hash="hash_onboarding_67890",
        platform="youtube",
        return_to="onboarding",
        expires_in_minutes=10,
    )
    assert state_onboarding.return_to == "onboarding"

    # Mark onboarding state as used
    mark_oauth_state_used(db_session, state_onboarding.state_hash)
    db_session.refresh(state_onboarding)
    assert state_onboarding.used_at is not None

    # 3. Create expired state
    state_expired = create_oauth_state(
        db=db_session,
        state_hash="hash_expired_00000",
        platform="youtube",
        return_to="settings",
        expires_in_minutes=-5,  # Already expired 5 min ago
    )
    expires_expired = (
        state_expired.expires_at.replace(tzinfo=UTC)
        if state_expired.expires_at.tzinfo is None
        else state_expired.expires_at
    )
    assert expires_expired < now

    # Check constraints: invalid return_to
    with pytest.raises(IntegrityError):
        create_oauth_state(
            db=db_session,
            state_hash="hash_invalid_return",
            platform="youtube",
            return_to="external_site",
        )
    db_session.rollback()

    # Cleanup expired and used rows (RET-01)
    deleted_count = cleanup_expired_or_used_oauth_states(db_session, now=now)
    assert deleted_count == 2  # state_onboarding (used) and state_expired (expired)

    # Unexpired unused state remains
    assert get_oauth_state(db_session, "hash_valid_12345") is not None
    assert get_oauth_state(db_session, "hash_onboarding_67890") is None
    assert get_oauth_state(db_session, "hash_expired_00000") is None


def test_deletion_jobs_lifecycle_and_creator_independence(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)

    # 1. Create deletion job
    initial_steps = [
        {"step": "stop_active_runs", "status": "PENDING", "error": None},
        {"step": "delete_tokens", "status": "PENDING", "error": None},
        {"step": "delete_application_rows", "status": "PENDING", "error": None},
    ]
    job = create_deletion_job(db_session, steps_json=initial_steps)
    assert job.id is not None
    assert job.status == "PENDING"
    assert len(job.steps_json) == 3
    assert job.finished_at is None

    # Check constraint: invalid status
    with pytest.raises(IntegrityError):
        update_deletion_job(db_session, job.id, status="INVALID_STATUS")
    db_session.rollback()

    # 2. Update to RUNNING
    updated_steps = [
        {"step": "stop_active_runs", "status": "COMPLETED", "error": None},
        {"step": "delete_tokens", "status": "RUNNING", "error": None},
        {"step": "delete_application_rows", "status": "PENDING", "error": None},
    ]
    update_deletion_job(db_session, job.id, status="RUNNING", steps_json=updated_steps)
    db_session.refresh(job)
    assert job.status == "RUNNING"
    assert job.steps_json[1]["status"] == "RUNNING"

    # 3. Update to COMPLETED
    update_deletion_job(db_session, job.id, status="COMPLETED")
    db_session.refresh(job)
    assert job.status == "COMPLETED"
    assert job.finished_at is not None

    # 4. Independence check: deleting creator does NOT delete deletion_job
    db_session.delete(creator)
    db_session.commit()

    # Deletion job remains accessible to report results (ADR-024)
    persisted_job = get_deletion_job(db_session, job.id)
    assert persisted_job is not None
    assert persisted_job.id == job.id
    assert persisted_job.status == "COMPLETED"
    assert get_latest_deletion_job(db_session) is not None
