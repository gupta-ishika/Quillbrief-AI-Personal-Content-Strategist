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
from app.db.repositories import create_plan_version, create_run
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


def _seed_plan(db: Session, run_id: str) -> ContentPlan:
    plan = create_plan_version(
        db=db,
        lineage_id="lineage_123",
        version=1,
        run_id=run_id,
        items=[
            {
                "topic": "System Design in Python",
                "format": "video",
                "platform": "youtube",
                "objective": "educational",
                "reason": "Top requested topic in audience comments",
                "source_type": "comment",
                "source_ref": "c1",
                "priority": 1,
            }
        ],
        created_by="strategist",
        status="PENDING_APPROVAL",
    )
    return plan


def test_list_approvals_and_filter(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    a1 = Approval(run_id=run.id, item_type="plan", item_id="plan_1", status="PENDING")
    a2 = Approval(
        run_id=run.id, item_type="draft", item_id="draft_1", status="DECIDED", decision="APPROVED"
    )
    db_session.add_all([a1, a2])
    db_session.commit()

    # List all
    res = client.get("/api/v1/approvals")
    assert res.status_code == 200
    approvals = res.json()
    assert len(approvals) == 2

    # Filter by status
    res_pending = client.get("/api/v1/approvals?status=PENDING")
    assert res_pending.status_code == 200
    assert len(res_pending.json()) == 1
    assert res_pending.json()[0]["id"] == a1.id

    # Filter by item_type
    res_draft = client.get("/api/v1/approvals?item_type=draft")
    assert res_draft.status_code == 200
    assert len(res_draft.json()) == 1
    assert res_draft.json()[0]["id"] == a2.id


def test_get_approval_by_id(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    plan = _seed_plan(db_session, run.id)
    approval = Approval(run_id=run.id, item_type="plan", item_id=plan.id, status="PENDING")
    db_session.add(approval)
    db_session.commit()

    res = client.get(f"/api/v1/approvals/{approval.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == approval.id
    assert data["item_type"] == "plan"
    assert data["item_id"] == plan.id
    assert data["item_details"] is not None
    assert len(data["item_details"]["items"]) == 1
    assert data["item_details"]["items"][0]["topic"] == "System Design in Python"


def test_get_approval_not_found(client: TestClient, db_session: Session) -> None:
    res = client.get("/api/v1/approvals/non-existent-id")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "APPROVAL_NOT_FOUND"


def test_decide_approval_approved(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    run.status = "WAITING_APPROVAL"
    plan = _seed_plan(db_session, run.id)
    approval = Approval(run_id=run.id, item_type="plan", item_id=plan.id, status="PENDING")
    db_session.add(approval)
    db_session.commit()

    res = client.post(
        f"/api/v1/approvals/{approval.id}/decision",
        json={"item_id": plan.id, "decision": "APPROVED"},
        headers=HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["approval"]["status"] == "DECIDED"
    assert data["approval"]["decision"] == "APPROVED"
    assert data["resulting_item_id"] == plan.id
    assert data["resumed_run_id"] == run.id

    # Verify plan status updated to APPROVED
    db_session.refresh(plan)
    assert plan.status == "APPROVED"
    assert plan.approved_at is not None

    # Verify run returned to RUNNING
    db_session.refresh(run)
    assert run.status == "RUNNING"


def test_decide_approval_rejected(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    plan = _seed_plan(db_session, run.id)
    approval = Approval(run_id=run.id, item_type="plan", item_id=plan.id, status="PENDING")
    db_session.add(approval)
    db_session.commit()

    # Missing feedback_text on REJECTED returns 422
    res_fail = client.post(
        f"/api/v1/approvals/{approval.id}/decision",
        json={"item_id": plan.id, "decision": "REJECTED"},
        headers=HEADERS,
    )
    assert res_fail.status_code == 422

    # Success with feedback_text
    res = client.post(
        f"/api/v1/approvals/{approval.id}/decision",
        json={
            "item_id": plan.id,
            "decision": "REJECTED",
            "feedback_text": "Need more beginner-friendly topics.",
        },
        headers=HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["approval"]["decision"] == "REJECTED"
    assert data["approval"]["feedback_text"] == "Need more beginner-friendly topics."

    db_session.refresh(plan)
    assert plan.status == "REJECTED"
    assert plan.feedback_text == "Need more beginner-friendly topics."


def test_decide_approval_edited(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    plan = _seed_plan(db_session, run.id)
    approval = Approval(run_id=run.id, item_type="plan", item_id=plan.id, status="PENDING")
    db_session.add(approval)
    db_session.commit()

    edited_items = [
        {
            "topic": "Python Async Internals",
            "format": "video",
            "platform": "youtube",
            "objective": "deep dive",
            "reason": "Edited by creator directly",
            "source_type": "own_idea",
            "priority": 1,
        }
    ]

    res = client.post(
        f"/api/v1/approvals/{approval.id}/decision",
        json={
            "item_id": plan.id,
            "decision": "EDITED",
            "edited_content": edited_items,
            "feedback_text": "Refined focus towards asyncio",
        },
        headers=HEADERS,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["approval"]["status"] == "DECIDED"
    assert data["approval"]["decision"] == "EDITED"

    new_plan_id = data["resulting_item_id"]
    assert new_plan_id is not None
    assert new_plan_id != plan.id

    # Check that previous plan is SUPERSEDED and new plan is APPROVED
    db_session.refresh(plan)
    assert plan.status == "SUPERSEDED"

    new_plan = db_session.query(ContentPlan).filter_by(id=new_plan_id).first()
    assert new_plan is not None
    assert new_plan.version == 2
    assert new_plan.created_by == "creator"
    assert new_plan.status == "APPROVED"
    assert new_plan.approved_at is not None
    assert len(new_plan.items) == 1
    assert new_plan.items[0].topic == "Python Async Internals"


def test_decide_approval_stale_errors(client: TestClient, db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    plan = _seed_plan(db_session, run.id)
    approval = Approval(run_id=run.id, item_type="plan", item_id=plan.id, status="PENDING")
    db_session.add(approval)
    db_session.commit()

    # Wrong item_id -> 409 STALE_APPROVAL
    res_mismatch = client.post(
        f"/api/v1/approvals/{approval.id}/decision",
        json={"item_id": "different_id", "decision": "APPROVED"},
        headers=HEADERS,
    )
    assert res_mismatch.status_code == 409
    assert res_mismatch.json()["error"]["code"] == "STALE_APPROVAL"

    # Already decided -> 409 STALE_APPROVAL
    approval.status = "DECIDED"
    db_session.commit()

    res_already = client.post(
        f"/api/v1/approvals/{approval.id}/decision",
        json={"item_id": plan.id, "decision": "APPROVED"},
        headers=HEADERS,
    )
    assert res_already.status_code == 409
    assert res_already.json()["error"]["code"] == "STALE_APPROVAL"
