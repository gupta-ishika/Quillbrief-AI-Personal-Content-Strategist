from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import Approval, RunEvent
from app.db.repositories import create_run
from app.services.recovery import recover_interrupted_runs


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
        Base.metadata.drop_all(test_engine)


def test_recover_running_runs_to_interrupted(db_session: Session) -> None:
    # 1. Setup runs in different states
    running_run = create_run(db_session, run_type="goal", depth_level="standard")
    running_run.status = "RUNNING"

    waiting_run = create_run(db_session, run_type="goal", depth_level="standard")
    waiting_run.status = "WAITING_APPROVAL"

    completed_run = create_run(db_session, run_type="goal", depth_level="standard")
    completed_run.status = "COMPLETED"

    db_session.commit()

    # 2. Execute recovery at startup
    recovered_ids = recover_interrupted_runs(db_session)

    # 3. Verify only RUNNING run was recovered
    assert recovered_ids == [running_run.id]

    db_session.refresh(running_run)
    db_session.refresh(waiting_run)
    db_session.refresh(completed_run)

    assert running_run.status == "INTERRUPTED"
    assert waiting_run.status == "WAITING_APPROVAL"
    assert completed_run.status == "COMPLETED"

    # 4. Verify recovery event recorded in run_events
    events = (
        db_session.query(RunEvent).filter_by(run_id=running_run.id, event_type="recovery").all()
    )
    assert len(events) == 1
    assert events[0].payload_json["previous_status"] == "RUNNING"
    assert "recovered_at" in events[0].payload_json


def test_pending_approvals_preserved_during_recovery(db_session: Session) -> None:
    waiting_run = create_run(db_session, run_type="goal", depth_level="standard")
    waiting_run.status = "WAITING_APPROVAL"

    app_waiting = Approval(run_id=waiting_run.id, item_type="plan", item_id="p1", status="PENDING")
    db_session.add(app_waiting)
    db_session.commit()

    # Recovery
    recover_interrupted_runs(db_session)

    db_session.refresh(waiting_run)
    db_session.refresh(app_waiting)

    # Invariant: Pending approvals are untouched by startup recovery
    assert waiting_run.status == "WAITING_APPROVAL"
    assert app_waiting.status == "PENDING"
