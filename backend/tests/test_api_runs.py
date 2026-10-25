from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.config import settings
from app.db.base import Base
from app.db.models import Approval, RoutingLog, Run
from app.db.repositories import (
    create_run,
    create_task,
    set_setting,
)
from app.db.session import get_db
from app.main import app


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
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(test_engine)


@pytest.fixture
def client(db_session: Session) -> TestClient:
    return TestClient(app)


HEADERS = {
    "Origin": settings.frontend_origin,
    "Content-Type": "application/json",
}


def test_start_run_onboarding_required(client: TestClient, db_session: Session) -> None:
    # Onboarding not completed
    response = client.post("/api/v1/runs", json={"goal_text": "Create 3 videos"}, headers=HEADERS)
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "ONBOARDING_REQUIRED"


def test_start_run_deletion_in_progress(client: TestClient, db_session: Session) -> None:
    set_setting(db_session, "onboarding_completed", True)
    set_setting(db_session, "deletion_in_progress", True)

    response = client.post("/api/v1/runs", json={"goal_text": "Create 3 videos"}, headers=HEADERS)
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "DELETION_IN_PROGRESS"


def test_start_run_active_conflict(client: TestClient, db_session: Session) -> None:
    set_setting(db_session, "onboarding_completed", True)
    # Create active running goal run
    active_run = create_run(db_session, run_type="goal", depth_level="standard")
    active_run.status = "RUNNING"
    db_session.commit()

    response = client.post("/api/v1/runs", json={"goal_text": "Another goal"}, headers=HEADERS)
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "RUN_ACTIVE"


def test_start_run_success(client: TestClient, db_session: Session) -> None:
    set_setting(db_session, "onboarding_completed", True)

    response = client.post(
        "/api/v1/runs",
        json={"goal_text": "Build personal brand in tech", "depth_level": "deep"},
        headers=HEADERS,
    )
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "PENDING"

    # Verify run persisted in database
    run = db_session.query(Run).filter_by(id=data["run_id"]).first()
    assert run is not None
    assert run.depth_level == "deep"
    assert run.run_type == "goal"


def test_list_runs_and_filtering(client: TestClient, db_session: Session) -> None:
    r1 = create_run(db_session, run_type="goal", depth_level="standard")
    r1.status = "COMPLETED"
    r2 = create_run(db_session, run_type="weekly_brief", depth_level="quick")
    r2.status = "RUNNING"
    db_session.commit()

    # List all
    res_all = client.get("/api/v1/runs")
    assert res_all.status_code == 200
    all_runs = res_all.json()
    assert len(all_runs) >= 2

    # Filter by status
    res_running = client.get("/api/v1/runs?status=RUNNING")
    assert res_running.status_code == 200
    running_runs = res_running.json()
    assert all(r["status"] == "RUNNING" for r in running_runs)
    assert any(r["id"] == r2.id for r in running_runs)

    # Filter by run_type
    res_brief = client.get("/api/v1/runs?run_type=weekly_brief")
    assert res_brief.status_code == 200
    brief_runs = res_brief.json()
    assert all(r["run_type"] == "weekly_brief" for r in brief_runs)


def test_get_run_by_id(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    t1 = create_task(
        db_session, run_id=run.id, title="Analyze comments", agent="listener", position=1
    )
    approval = Approval(run_id=run.id, item_type="plan", item_id="plan_xyz", status="PENDING")
    db_session.add(approval)
    db_session.commit()

    response = client.get(f"/api/v1/runs/{run.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == run.id
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["id"] == t1.id
    assert data["pending_approval_id"] == approval.id


def test_get_run_not_found(client: TestClient, db_session: Session) -> None:
    response = client.get("/api/v1/runs/non-existent-id")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "RUN_NOT_FOUND"


def test_get_run_routing_log(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    log1 = RoutingLog(
        run_id=run.id,
        step_number=1,
        from_node="START",
        to_node="listener",
        reason="Initial listener step",
        decided_by="model",
        eligible_nodes_json=["listener", "research"],
        output_status="valid",
        invalid_category=None,
        tokens_in=100,
        tokens_out=20,
    )
    db_session.add(log1)
    db_session.commit()

    response = client.get(f"/api/v1/runs/{run.id}/routing-log")
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 1
    assert logs[0]["step_number"] == 1
    assert logs[0]["to_node"] == "listener"
    assert logs[0]["eligible_nodes"] == ["listener", "research"]


def test_cancel_run(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    run.status = "RUNNING"
    app1 = Approval(run_id=run.id, item_type="plan", item_id="plan_cancel", status="PENDING")
    db_session.add(app1)
    db_session.commit()

    response = client.post(f"/api/v1/runs/{run.id}/cancel", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "STOPPED"
    assert data["stop_reason"] == "Cancelled by user"

    # Pending approval must be CANCELLED
    db_session.refresh(app1)
    assert app1.status == "CANCELLED"

    # Cancel already finished run returns 409
    res_again = client.post(f"/api/v1/runs/{run.id}/cancel", headers=HEADERS)
    assert res_again.status_code == 409
    assert res_again.json()["error"]["code"] == "RUN_ALREADY_FINISHED"


def test_resume_run(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    run.status = "INTERRUPTED"
    db_session.commit()

    response = client.post(f"/api/v1/runs/{run.id}/resume", headers=HEADERS)
    assert response.status_code == 202
    data = response.json()
    assert data["run_id"] == run.id
    assert data["status"] == "RUNNING"

    # Resume running run returns 409 RUN_NOT_RESUMABLE
    res_bad = client.post(f"/api/v1/runs/{run.id}/resume", headers=HEADERS)
    assert res_bad.status_code == 409
    assert res_bad.json()["error"]["code"] == "RUN_NOT_RESUMABLE"
