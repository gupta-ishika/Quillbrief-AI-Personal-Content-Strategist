import os
import tempfile
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.repositories.settings import set_setting
from app.scheduler import (
    WEEKLY_BRIEF_JOB_ID,
    get_next_brief_time,
    get_scheduler,
    is_scheduler_running,
    normalize_day_of_week,
    parse_time_string,
    placeholder_weekly_brief_job,
    remove_all_jobs,
    remove_weekly_brief_job,
    reset_scheduler,
    resolve_time_zone,
    start_scheduler,
    stop_scheduler,
    sync_weekly_brief_job,
)


@pytest.fixture(autouse=True)
def clean_scheduler() -> Generator[None, None, None]:
    reset_scheduler()
    yield
    reset_scheduler()


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_sched.db")
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)
        session = session_factory()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()


def test_scheduler_lifecycle() -> None:
    sched = get_scheduler()
    assert not is_scheduler_running()
    start_scheduler()
    assert is_scheduler_running()
    assert sched.running
    stop_scheduler()
    assert not is_scheduler_running()


def test_normalize_day_of_week() -> None:
    assert normalize_day_of_week("mon") == "mon"
    assert normalize_day_of_week("Monday") == "mon"
    assert normalize_day_of_week("TUESDAY") == "tue"
    assert normalize_day_of_week("fri") == "fri"
    assert normalize_day_of_week("unknown_day") == "mon"
    assert normalize_day_of_week(None) == "mon"


def test_parse_time_string() -> None:
    assert parse_time_string("08:00") == (8, 0)
    assert parse_time_string("14:45") == (14, 45)
    assert parse_time_string("00:00") == (0, 0)
    assert parse_time_string("invalid") == (8, 0)
    assert parse_time_string("25:99") == (8, 0)
    assert parse_time_string(None) == (8, 0)


def test_resolve_time_zone() -> None:
    tz1 = resolve_time_zone("Asia/Kolkata")
    assert str(tz1) == "Asia/Kolkata"

    tz2 = resolve_time_zone("UTC")
    assert str(tz2) == "UTC"

    tz3 = resolve_time_zone("Invalid/Timezone_Name")
    assert str(tz3) in ("Asia/Kolkata", "UTC")


def test_weekly_brief_not_created_until_onboarding_completed(test_db: Session) -> None:
    """Invariant: Creates no job until onboarding is completed (SCHED-00, PRD, ADR-022)."""
    start_scheduler()

    # Settings exist but onboarding_completed is False
    set_setting(test_db, "brief_day", "mon")
    set_setting(test_db, "brief_time", "08:00")
    set_setting(test_db, "time_zone", "Asia/Kolkata")
    set_setting(test_db, "onboarding_completed", False)

    next_time = sync_weekly_brief_job(db=test_db)
    assert next_time is None
    assert get_next_brief_time() is None

    sched = get_scheduler()
    job = sched.get_job(WEEKLY_BRIEF_JOB_ID)
    assert job is None


def test_weekly_brief_created_on_onboarding_complete(test_db: Session) -> None:
    """Invariant: Completing onboarding creates the Weekly Brief job (SCHED-00, API.md)."""
    start_scheduler()

    set_setting(test_db, "brief_day", "mon")
    set_setting(test_db, "brief_time", "08:00")
    set_setting(test_db, "time_zone", "Asia/Kolkata")
    set_setting(test_db, "onboarding_completed", True)

    next_time = sync_weekly_brief_job(db=test_db)
    assert next_time is not None
    assert "2026-" in next_time
    assert get_next_brief_time() == next_time

    sched = get_scheduler()
    job = sched.get_job(WEEKLY_BRIEF_JOB_ID)
    assert job is not None
    assert job.id == WEEKLY_BRIEF_JOB_ID
    assert job.name == "Weekly Brief"


def test_weekly_brief_replaced_on_schedule_change(test_db: Session) -> None:
    """Invariant: Changing settings replaces the scheduler job immediately (DECISIONS.md, ARCHITECTURE.md)."""
    start_scheduler()

    set_setting(test_db, "onboarding_completed", True)
    set_setting(test_db, "brief_day", "mon")
    set_setting(test_db, "brief_time", "08:00")
    set_setting(test_db, "time_zone", "UTC")
    time_1 = sync_weekly_brief_job(db=test_db)

    # Change to Friday 15:30
    set_setting(test_db, "brief_day", "fri")
    set_setting(test_db, "brief_time", "15:30")
    time_2 = sync_weekly_brief_job(db=test_db)

    assert time_2 is not None
    assert time_2 != time_1


def test_weekly_brief_removed_if_onboarding_incomplete(test_db: Session) -> None:
    """If onboarding is reset (e.g. data deletion), job is removed."""
    start_scheduler()

    set_setting(test_db, "onboarding_completed", True)
    set_setting(test_db, "brief_day", "mon")
    sync_weekly_brief_job(db=test_db)
    assert get_next_brief_time() is not None

    # Reset onboarding
    set_setting(test_db, "onboarding_completed", False)
    next_time = sync_weekly_brief_job(db=test_db)
    assert next_time is None
    assert get_next_brief_time() is None

    sched = get_scheduler()
    assert sched.get_job(WEEKLY_BRIEF_JOB_ID) is None


def test_remove_all_jobs_for_creator_deletion(test_db: Session) -> None:
    """ADR-024 / DATABASE.md Section 11: Remove all scheduler jobs."""
    start_scheduler()

    set_setting(test_db, "onboarding_completed", True)
    sync_weekly_brief_job(db=test_db)
    assert get_next_brief_time() is not None

    removed = remove_all_jobs()
    assert removed >= 1
    assert get_next_brief_time() is None


def test_remove_weekly_brief_job_handles_nonexistent() -> None:
    start_scheduler()
    # Removing when not present should return False and not raise
    assert remove_weekly_brief_job() is False


def test_placeholder_target_executes() -> None:
    """Placeholder target callable executes without error (AGT-07)."""
    placeholder_weekly_brief_job()
