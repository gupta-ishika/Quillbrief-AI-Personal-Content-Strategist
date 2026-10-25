from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.config import settings
from app.db.base import Base
from app.db.models import Approval, ContentPlan
from app.db.repositories import create_approval, create_plan_version, create_run
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


def test_get_plan_details(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    plan = create_plan_version(
        db=db_session,
        lineage_id="lineage_v1",
        version=1,
        run_id=run.id,
        items=[
            {
                "item_key": "k1",
                "topic": "Python Memory Profiling",
                "format": "video",
                "platform": "youtube",
                "objective": "educational",
                "reason": "Audience request",
                "source_type": "comment",
                "priority": 1,
            }
        ],
        created_by="strategist",
        status="PENDING_APPROVAL",
    )

    res = client.get(f"/api/v1/plans/{plan.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == plan.id
    assert data["version"] == 1
    assert data["is_latest"] is True
    assert len(data["items"]) == 1
    assert data["items"][0]["item_key"] == "k1"


def test_edit_plan_stale_version_error(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    plan = create_plan_version(
        db=db_session,
        lineage_id="lineage_v2",
        version=1,
        run_id=run.id,
        items=[
            {
                "topic": "Intro to Docker",
                "format": "video",
                "platform": "youtube",
                "objective": "educational",
                "reason": "Popular trend",
            }
        ],
        status="PENDING_APPROVAL",
    )

    # Edit with expected_version = 2 (when current is 1)
    payload = {
        "expected_version": 2,
        "items": [
            {
                "topic": "Intro to Podman",
                "format": "video",
                "platform": "youtube",
                "objective": "educational",
                "reason": "Alternative to Docker",
            }
        ],
    }

    res = client.post(f"/api/v1/plans/{plan.id}/edit", json=payload, headers=HEADERS)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "STALE_VERSION"


def test_edit_plan_creates_new_version_and_approval(
    client: TestClient, db_session: Session
) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    plan_v1 = create_plan_version(
        db=db_session,
        lineage_id="lineage_v3",
        version=1,
        run_id=run.id,
        items=[
            {
                "item_key": "stable_key_1",
                "topic": "Python Profiling",
                "format": "video",
                "platform": "youtube",
                "objective": "educational",
                "reason": "High interest",
            }
        ],
        status="PENDING_APPROVAL",
    )
    app_v1 = create_approval(db_session, item_type="plan", item_id=plan_v1.id, run_id=run.id)

    # Creator edits the plan outside an approval decision
    edit_payload = {
        "expected_version": 1,
        "items": [
            {
                "item_key": "stable_key_1",
                "topic": "Advanced Python Profiling with cProfile",
                "format": "video",
                "platform": "youtube",
                "objective": "educational",
                "reason": "Refined focus",
                "source_type": "own_idea",
                "priority": 1,
            },
            {
                "topic": "Async Profiling in Python",
                "format": "video",
                "platform": "youtube",
                "objective": "educational",
                "reason": "Added new item",
                "source_type": "own_idea",
                "priority": 2,
            },
        ],
    }

    res = client.post(f"/api/v1/plans/{plan_v1.id}/edit", json=edit_payload, headers=HEADERS)
    assert res.status_code == 201
    data = res.json()
    new_plan_id = data["plan_id"]
    new_approval_id = data["approval_id"]

    assert new_plan_id != plan_v1.id
    assert new_approval_id != app_v1.id

    # 1. Verify previous plan is SUPERSEDED and previous approval is CANCELLED
    db_session.refresh(plan_v1)
    db_session.refresh(app_v1)
    assert plan_v1.status == "SUPERSEDED"
    assert app_v1.status == "CANCELLED"

    # 2. Verify new plan is version 2, PENDING_APPROVAL, authored by creator
    plan_v2 = db_session.query(ContentPlan).filter_by(id=new_plan_id).first()
    assert plan_v2 is not None
    assert plan_v2.version == 2
    assert plan_v2.lineage_id == plan_v1.lineage_id
    assert plan_v2.previous_version_id == plan_v1.id
    assert plan_v2.created_by == "creator"
    assert plan_v2.status == "PENDING_APPROVAL"
    assert len(plan_v2.items) == 2

    # Check that stable_key_1 was preserved and the second item got a generated key
    item_keys = [it.item_key for it in plan_v2.items]
    assert "stable_key_1" in item_keys

    # 3. Verify new approval request references the exact version 2
    new_app = db_session.query(Approval).filter_by(id=new_approval_id).first()
    assert new_app is not None
    assert new_app.item_id == plan_v2.id
    assert new_app.status == "PENDING"


def test_exact_version_approvals_superseded_rejection(
    client: TestClient, db_session: Session
) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    plan_v1 = create_plan_version(
        db=db_session,
        lineage_id="lineage_v4",
        version=1,
        run_id=run.id,
        items=[
            {
                "topic": "Kubernetes 101",
                "format": "video",
                "platform": "youtube",
                "objective": "educational",
                "reason": "Cloud native trend",
            }
        ],
        status="PENDING_APPROVAL",
    )
    app_v1 = create_approval(db_session, item_type="plan", item_id=plan_v1.id, run_id=run.id)

    # Edit creates version 2
    client.post(
        f"/api/v1/plans/{plan_v1.id}/edit",
        json={
            "expected_version": 1,
            "items": [
                {
                    "topic": "Kubernetes 101: Pods & Deployments",
                    "format": "video",
                    "platform": "youtube",
                    "objective": "educational",
                    "reason": "Refined",
                }
            ],
        },
        headers=HEADERS,
    )

    # Attempting to decide the old approval returns 409 STALE_APPROVAL
    res = client.post(
        f"/api/v1/approvals/{app_v1.id}/decision",
        json={"item_id": plan_v1.id, "decision": "APPROVED"},
        headers=HEADERS,
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "STALE_APPROVAL"
