"""Integration tests for Insights, Findings, and Strategy API (API-04, API.md Section 6).

Validates:
- GET /insights/comments and GET /insights (Channel rule ADR-032, Comment retention ADR-033)
- GET /findings with draft_id, run_id, and single finding by ID
- GET /strategy with active entries and ?include=history for superseded entries
- Single strategy entry by key with 404 handling
"""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.base import Base
from app.db.models import Comment, ContentItem
from app.db.repositories.analytics import (
    create_analyst_finding,
    create_or_update_strategy_entry,
)
from app.db.repositories.content import create_comment_insight
from app.db.repositories.creator import get_or_create_creator, update_creator_channel
from app.db.repositories.plans import create_draft_version
from app.db.repositories.runs import create_goal, create_run
from app.db.session import get_db
from app.main import app as fastapi_app

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

    fastapi_app.dependency_overrides[get_db] = override_get_db
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(fastapi_app) as test_client:
        yield test_client


def test_comment_insights_channel_rule_and_retention(db_session: Session, client: TestClient) -> None:
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Test Channel Insights")
    run = create_run(db_session, goal_id=goal.id)

    # 1. Without saved channel, GET /insights/comments returns empty list (Channel Rule)
    res = client.get("/api/v1/insights/comments", headers=HEADERS)
    assert res.status_code == 200
    assert res.json() == []

    # Create content item from channel UC_OWN_1
    item_own = ContentItem(
        creator_id=creator.id,
        platform="youtube",
        external_id="vid_own_1",
        channel_external_id="UC_OWN_1",
        owner_type="own",
        title="Own Video 1",
        published_at=datetime.now(UTC),
    )
    # Create content item from other channel UC_OTHER
    item_other = ContentItem(
        creator_id=creator.id,
        platform="youtube",
        external_id="vid_other_1",
        channel_external_id="UC_OTHER",
        owner_type="similar",
        title="Other Video 1",
        published_at=datetime.now(UTC),
    )
    db_session.add_all([item_own, item_other])
    db_session.commit()

    # Create comments: one active text, one cleared text (>90 days)
    comment_active = Comment(
        content_item_id=item_own.id,
        external_id="c_active_1",
        text="Explain asyncio locks please!",
        like_count=15,
        published_at=datetime.now(UTC),
    )
    comment_cleared = Comment(
        content_item_id=item_own.id,
        external_id="c_cleared_1",
        text=None,  # Cleared by retention
        like_count=8,
        published_at=datetime.now(UTC),
    )
    db_session.add_all([comment_active, comment_cleared])
    db_session.commit()

    # Create insight for own item
    insight_own = create_comment_insight(
        db=db_session,
        creator_id=creator.id,
        run_id=run.id,
        theme_label="Asyncio Explanations",
        comment_count=23,
        coverage_analyzed=100,
        coverage_total=100,
        source_item_ids=[item_own.id],
        example_comment_ids=[comment_active.id, comment_cleared.id],
    )

    # Create insight for other item
    _insight_other = create_comment_insight(
        db=db_session,
        creator_id=creator.id,
        run_id=run.id,
        theme_label="Competitor Theme",
        comment_count=50,
        coverage_analyzed=100,
        coverage_total=100,
        source_item_ids=[item_other.id],
        example_comment_ids=[],
    )

    # 2. Channel set to UC_OWN_1
    update_creator_channel(db_session, channel_id="UC_OWN_1", channel_handle="@mychan", channel_title="My Channel", verified=True)

    res = client.get("/api/v1/insights/comments", headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    theme = data[0]
    assert theme["id"] == insight_own.id
    assert theme["theme_label"] == "Asyncio Explanations"
    assert theme["comment_count"] == 23

    # Check example comments retention behavior
    examples = theme["examples"]
    assert len(examples) == 2
    ex_active = next(e for e in examples if e["comment_id"] == comment_active.id)
    assert ex_active["available"] is True
    assert ex_active["text"] == "Explain asyncio locks please!"
    assert ex_active["like_count"] == 15

    ex_cleared = next(e for e in examples if e["comment_id"] == comment_cleared.id)
    assert ex_cleared["available"] is False
    assert ex_cleared["text"] is None
    assert ex_cleared["like_count"] == 8

    # Alias /api/v1/insights also works
    res_alias = client.get("/api/v1/insights", headers=HEADERS)
    assert res_alias.status_code == 200
    assert len(res_alias.json()) == 1


def test_findings_endpoints(db_session: Session, client: TestClient) -> None:
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Test Findings API")
    run = create_run(db_session, goal_id=goal.id)

    draft = create_draft_version(
        db=db_session,
        lineage_id="lineage-f-1",
        version=1,
        kind="script",
        platform="youtube",
        content="Hello world",
        created_by="model",
    )

    # Create two findings: one linked to draft, one standalone
    f1 = create_analyst_finding(
        db=db_session,
        run_id=run.id,
        draft_id=draft.id,
        finding="First 30s drop-off reduced by 22% when hook is under 15s",
        recommendation="Keep hooks under 15s across tutorials",
        confidence="high",
        sample_size=12,
        evidence_json={"hook_duration_s": 12, "retention_pct": 68.5},
    )

    f2 = create_analyst_finding(
        db=db_session,
        run_id=run.id,
        draft_id=None,
        finding="Weekend uploads correlate with lower comments",
        recommendation="Schedule weekday mornings",
        confidence="moderate",
        sample_size=5,
        evidence_json={},
    )

    # 1. GET /api/v1/findings
    res = client.get("/api/v1/findings", headers=HEADERS)
    assert res.status_code == 200
    findings = res.json()
    assert len(findings) == 2

    # Check linked draft
    f1_resp = next(f for f in findings if f["id"] == f1.id)
    assert f1_resp["finding"] == "First 30s drop-off reduced by 22% when hook is under 15s"
    assert f1_resp["confidence"] == "high"
    assert f1_resp["sample_size"] == 12
    assert f1_resp["draft_id"] == draft.id
    assert f1_resp["evidence"]["hook_duration_s"] == 12

    f2_resp = next(f for f in findings if f["id"] == f2.id)
    assert f2_resp["draft_id"] is None

    # 2. Filter by draft_id
    res_draft = client.get(f"/api/v1/findings?draft_id={draft.id}", headers=HEADERS)
    assert res_draft.status_code == 200
    data_draft = res_draft.json()
    assert len(data_draft) == 1
    assert data_draft[0]["id"] == f1.id

    # 3. Filter by run_id
    res_run = client.get(f"/api/v1/findings?run_id={run.id}", headers=HEADERS)
    assert res_run.status_code == 200
    assert len(res_run.json()) == 2

    # 4. GET /api/v1/findings/{id}
    res_single = client.get(f"/api/v1/findings/{f1.id}", headers=HEADERS)
    assert res_single.status_code == 200
    assert res_single.json()["id"] == f1.id

    # 5. 404 for unknown finding ID
    res_404 = client.get("/api/v1/findings/non-existent-id", headers=HEADERS)
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "FINDING_NOT_FOUND"


def test_strategy_endpoints(db_session: Session, client: TestClient) -> None:
    creator = get_or_create_creator(db_session)

    # Initially empty
    res_init = client.get("/api/v1/strategy", headers=HEADERS)
    assert res_init.status_code == 200
    assert res_init.json() == []

    # Create active entry
    entry1 = create_or_update_strategy_entry(
        db=db_session,
        creator_id=creator.id,
        key="preferred_format",
        value_json={"format": "video_script", "max_duration_min": 15},
        reason="Tutorials perform best as 10-15 minute deep dives",
        supporting_finding_ids_json=["find-1", "find-2"],
    )

    # Create second active entry
    _entry2 = create_or_update_strategy_entry(
        db=db_session,
        creator_id=creator.id,
        key="target_audience",
        value_json={"level": "intermediate", "tech": "Python"},
        reason="Audience requests intermediate Python content",
    )

    # 1. GET /api/v1/strategy returns both active
    res = client.get("/api/v1/strategy", headers=HEADERS)
    assert res.status_code == 200
    entries = res.json()
    assert len(entries) == 2
    keys = {e["key"] for e in entries}
    assert keys == {"preferred_format", "target_audience"}

    # 2. Update preferred_format -> supersedes entry1, creates entry1_v2
    entry1_v2 = create_or_update_strategy_entry(
        db=db_session,
        creator_id=creator.id,
        key="preferred_format",
        value_json={"format": "video_script", "max_duration_min": 10},
        reason="Updated: Retention drops past 10 minutes",
        supporting_finding_ids_json=["find-3"],
    )

    # GET /api/v1/strategy still returns 2 active entries
    res_active = client.get("/api/v1/strategy", headers=HEADERS)
    assert res_active.status_code == 200
    active_data = res_active.json()
    assert len(active_data) == 2
    pref = next(e for e in active_data if e["key"] == "preferred_format")
    assert pref["id"] == entry1_v2.id
    assert pref["value"]["max_duration_min"] == 10
    assert pref["reason"] == "Updated: Retention drops past 10 minutes"
    assert pref["supporting_finding_ids"] == ["find-3"]
    assert pref["status"] == "active"

    # 3. GET /api/v1/strategy?include=history returns 3 entries (including superseded entry1)
    res_hist = client.get("/api/v1/strategy?include=history", headers=HEADERS)
    assert res_hist.status_code == 200
    hist_data = res_hist.json()
    assert len(hist_data) == 3
    superseded = [e for e in hist_data if e["status"] == "superseded"]
    assert len(superseded) == 1
    assert superseded[0]["id"] == entry1.id

    # 4. GET /api/v1/strategy/{key} returns active entry
    res_key = client.get("/api/v1/strategy/preferred_format", headers=HEADERS)
    assert res_key.status_code == 200
    assert res_key.json()["id"] == entry1_v2.id

    # 5. GET /api/v1/strategy/{unknown_key} returns 404
    res_key_404 = client.get("/api/v1/strategy/unknown_key", headers=HEADERS)
    assert res_key_404.status_code == 404
    assert res_key_404.json()["error"]["code"] == "STRATEGY_NOT_FOUND"
