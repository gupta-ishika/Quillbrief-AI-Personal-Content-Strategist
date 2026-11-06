"""Integration tests for Drafts API and Versioning (VER-02, API-03, UT-11, UT-18).

Validates:
- GET /drafts with filters (status, kind, platform, is_latest)
- GET /drafts/{draft_id} and GET /drafts/{draft_id}/versions
- POST /drafts/{draft_id}/edit with deterministic check and approval creation
- POST /drafts/{draft_id}/mark-posted (APPROVED only, latest only, posted_ref)
- POST /drafts/{draft_id}/link-posted (POSTED only)
- Stale version and unapproved 409 conflict handling
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.config import settings
from app.db.base import Base, generate_uuid
from app.db.models import Approval, Draft
from app.db.repositories.plans import create_draft_version
from app.db.session import get_db
from app.main import app

HEADERS = {
    "Origin": settings.frontend_origin,
    "Content-Type": "application/json",
}


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


def test_list_and_get_drafts_with_filters(client: TestClient, db_session: Session) -> None:
    lineage1 = generate_uuid()
    lineage2 = generate_uuid()

    # Draft 1: YouTube script, APPROVED
    d1 = create_draft_version(
        db=db_session,
        lineage_id=lineage1,
        version=1,
        kind="script",
        platform="youtube",
        content="# Hook\nHook\n\n# Body\nBody\n\n# CTA\nSubscribe",
        status="APPROVED",
    )

    # Draft 2: Revision of lineage 1, IN_REVIEW
    d2 = create_draft_version(
        db=db_session,
        lineage_id=lineage1,
        version=2,
        kind="script",
        platform="youtube",
        content="# Hook\nHook 2\n\n# Body\nBody 2\n\n# CTA\nSubscribe",
        previous_version_id=d1.id,
        status="IN_REVIEW",
    )

    # Draft 3: Instagram caption, APPROVED
    d3 = create_draft_version(
        db=db_session,
        lineage_id=lineage2,
        version=1,
        kind="caption",
        platform="instagram",
        content="Instagram caption text #tag",
        status="APPROVED",
    )

    # 1. List all
    res = client.get("/api/v1/drafts")
    assert res.status_code == 200
    all_drafts = res.json()
    assert len(all_drafts) == 3

    # 2. Filter by platform
    res_platform = client.get("/api/v1/drafts?platform=instagram")
    assert res_platform.status_code == 200
    assert len(res_platform.json()) == 1
    assert res_platform.json()[0]["id"] == d3.id

    # 3. Filter by is_latest
    res_latest = client.get("/api/v1/drafts?is_latest=true")
    assert res_latest.status_code == 200
    latest_ids = {d["id"] for d in res_latest.json()}
    assert latest_ids == {d2.id, d3.id}

    # 4. Get by ID
    res_single = client.get(f"/api/v1/drafts/{d1.id}")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == d1.id
    assert res_single.json()["is_latest"] is False

    # 5. Get versions
    res_versions = client.get(f"/api/v1/drafts/{d2.id}/versions")
    assert res_versions.status_code == 200
    versions = res_versions.json()
    assert len(versions) == 2
    assert versions[0]["version"] == 2
    assert versions[1]["version"] == 1


def test_edit_draft_outside_approval(client: TestClient, db_session: Session) -> None:
    lineage = generate_uuid()
    draft = create_draft_version(
        db=db_session,
        lineage_id=lineage,
        version=1,
        kind="script",
        platform="youtube",
        content="# Hook\nOriginal hook\n\n# Body\nOriginal body\n\n# CTA\nOriginal CTA",
        status="APPROVED",
    )
    old_approval = Approval(item_type="draft", item_id=draft.id, status="PENDING")
    db_session.add(old_approval)
    db_session.commit()

    # 1. Deterministic checks failure (missing CTA)
    bad_edit = {
        "content": "# Hook\nOnly hook without body or cta.",
        "expected_version": 1,
    }
    res_bad = client.post(f"/api/v1/drafts/{draft.id}/edit", json=bad_edit, headers=HEADERS)
    assert res_bad.status_code == 422
    assert res_bad.json()["error"]["code"] == "CHECKS_FAILED"

    # 2. Stale version failure (expected 2 when current is 1)
    res_stale = client.post(
        f"/api/v1/drafts/{draft.id}/edit",
        json={
            "content": "# Hook\nHook\n\n# Body\nBody\n\n# CTA\nCTA",
            "expected_version": 2,
        },
        headers=HEADERS,
    )
    assert res_stale.status_code == 409
    assert res_stale.json()["error"]["code"] == "STALE_VERSION"

    # 3. Successful edit
    valid_edit = {
        "content": "# Hook\nEdited by creator\n\n# Body\nCreator refined the body text\n\n# CTA\nSubscribe for updates!",
        "expected_version": 1,
    }
    res_ok = client.post(f"/api/v1/drafts/{draft.id}/edit", json=valid_edit, headers=HEADERS)
    assert res_ok.status_code == 201
    data = res_ok.json()
    new_draft_id = data["draft_id"]
    approval_id = data["approval_id"]

    # Verify previous version is SUPERSEDED
    db_session.refresh(draft)
    assert draft.status == "SUPERSEDED"

    # Verify old approval is CANCELLED
    db_session.refresh(old_approval)
    assert old_approval.status == "CANCELLED"

    # Verify new version created in PENDING_APPROVAL
    new_draft = db_session.query(Draft).filter_by(id=new_draft_id).first()
    assert new_draft is not None
    assert new_draft.version == 2
    assert new_draft.created_by == "creator"
    assert new_draft.status == "PENDING_APPROVAL"
    assert new_draft.previous_version_id == draft.id

    # Verify new approval record exists
    new_app = db_session.query(Approval).filter_by(id=approval_id).first()
    assert new_app is not None
    assert new_app.item_id == new_draft_id
    assert new_app.status == "PENDING"


def test_mark_draft_as_posted_and_link(client: TestClient, db_session: Session) -> None:
    lineage = generate_uuid()
    draft = create_draft_version(
        db=db_session,
        lineage_id=lineage,
        version=1,
        kind="script",
        platform="youtube",
        content="# Hook\nHook\n\n# Body\nBody\n\n# CTA\nCTA",
        status="IN_REVIEW",  # Not yet approved
    )

    # 1. Fails when draft is not APPROVED
    res_not_approved = client.post(
        f"/api/v1/drafts/{draft.id}/mark-posted",
        json={},
        headers=HEADERS,
    )
    assert res_not_approved.status_code == 409
    assert res_not_approved.json()["error"]["code"] == "NOT_APPROVED"

    # Update to APPROVED
    draft.status = "APPROVED"
    db_session.commit()

    # 2. Mark posted without links (posted_ref = none)
    res_posted = client.post(
        f"/api/v1/drafts/{draft.id}/mark-posted",
        json={},
        headers=HEADERS,
    )
    assert res_posted.status_code == 200
    post_data = res_posted.json()
    assert post_data["status"] == "POSTED"
    assert post_data["posted_ref"] == "none"
    assert post_data["analytics_eligible"] is False

    db_session.refresh(draft)
    assert draft.status == "POSTED"
    assert draft.posted_at is not None

    # 3. Add link via link-posted
    res_link = client.post(
        f"/api/v1/drafts/{draft.id}/link-posted",
        json={"posted_url": "https://youtube.com/watch?v=abc123xyz"},
        headers=HEADERS,
    )
    assert res_link.status_code == 200
    linked_data = res_link.json()
    assert linked_data["posted_url"] == "https://youtube.com/watch?v=abc123xyz"
    assert linked_data["posted_ref"] == "url"

    db_session.refresh(draft)
    assert draft.posted_ref == "url"


def test_mark_posted_stale_version_failure(client: TestClient, db_session: Session) -> None:
    lineage = generate_uuid()
    d1 = create_draft_version(
        db=db_session,
        lineage_id=lineage,
        version=1,
        kind="script",
        platform="youtube",
        content="# Hook\nHook 1\n\n# Body\nBody 1\n\n# CTA\nCTA 1",
        status="APPROVED",
    )
    create_draft_version(
        db=db_session,
        lineage_id=lineage,
        version=2,
        kind="script",
        platform="youtube",
        content="# Hook\nHook 2\n\n# Body\nBody 2\n\n# CTA\nCTA 2",
        previous_version_id=d1.id,
        status="APPROVED",
    )

    # Attempting to mark outdated version 1 as posted must return 409 STALE_VERSION
    res = client.post(
        f"/api/v1/drafts/{d1.id}/mark-posted",
        json={},
        headers=HEADERS,
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "STALE_VERSION"
