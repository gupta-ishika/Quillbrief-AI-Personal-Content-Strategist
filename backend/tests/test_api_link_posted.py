"""Tests for link-posted endpoint and Analyst unlinked post skipping (API-07, IT-23, PRD FR-11).

Validates:
- POST /api/v1/drafts/{id}/link-posted validation (NOT_POSTED 409, LINK_REQUIRED 422, DRAFT_NOT_FOUND 404)
- Successful link attachment via URL or platform ID
- Analyst skips unlinked posts with a clear message and produces no misleading analytics
- Analyst successfully analyzes draft once linked via link-posted
- Matching is strictly by URL or platform ID, never by title alone
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.analyst import analyst_node
from app.config import settings
from app.db.base import Base
from app.db.repositories.analytics import create_performance_metric
from app.db.repositories.creator import get_or_create_creator
from app.db.repositories.plans import create_draft_version
from app.db.repositories.runs import create_goal, create_run
from app.db.session import get_db
from app.graph.state import ContentState
from app.main import app as fastapi_app
from app.tools.analyst_tools import db_load_metrics_tool, extract_youtube_video_id

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


def test_link_posted_validation_and_linking(db_session: Session, client: TestClient) -> None:
    # 1. 404 for unknown draft
    res_404 = client.post(
        "/api/v1/drafts/non-existent-draft/link-posted",
        json={"posted_url": "https://youtube.com/watch?v=abc12345678"},
        headers=HEADERS,
    )
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "DRAFT_NOT_FOUND"

    # Create an APPROVED (not yet POSTED) draft
    draft_approved = create_draft_version(
        db=db_session,
        lineage_id="lineage-lp-1",
        version=1,
        kind="script",
        platform="youtube",
        content="# Script",
        created_by="model",
        status="APPROVED",
    )

    # 2. 409 NOT_POSTED if draft is not yet posted
    res_not_posted = client.post(
        f"/api/v1/drafts/{draft_approved.id}/link-posted",
        json={"posted_url": "https://youtube.com/watch?v=abc12345678"},
        headers=HEADERS,
    )
    assert res_not_posted.status_code == 409
    assert res_not_posted.json()["error"]["code"] == "NOT_POSTED"

    # Mark as posted with posted_ref == "none"
    res_mark = client.post(
        f"/api/v1/drafts/{draft_approved.id}/mark-posted",
        json={},
        headers=HEADERS,
    )
    assert res_mark.status_code == 200
    assert res_mark.json()["posted_ref"] == "none"

    # 3. 422 LINK_REQUIRED if neither URL nor ID provided
    res_no_link = client.post(
        f"/api/v1/drafts/{draft_approved.id}/link-posted",
        json={},
        headers=HEADERS,
    )
    assert res_no_link.status_code == 422
    assert res_no_link.json()["error"]["code"] == "LINK_REQUIRED"

    # 4. Link via URL
    res_url = client.post(
        f"/api/v1/drafts/{draft_approved.id}/link-posted",
        json={"posted_url": "https://youtube.com/watch?v=dQw4w9WgXcQ"},
        headers=HEADERS,
    )
    assert res_url.status_code == 200
    data_url = res_url.json()
    assert data_url["posted_ref"] == "url"
    assert data_url["posted_url"] == "https://youtube.com/watch?v=dQw4w9WgXcQ"

    db_session.refresh(draft_approved)
    assert draft_approved.posted_ref == "url"
    assert draft_approved.posted_url == "https://youtube.com/watch?v=dQw4w9WgXcQ"

    # 5. Link via platform ID
    res_pid = client.post(
        f"/api/v1/drafts/{draft_approved.id}/link-posted",
        json={"platform_content_id": "dQw4w9WgXcQ"},
        headers=HEADERS,
    )
    assert res_pid.status_code == 200
    data_pid = res_pid.json()
    assert data_pid["posted_ref"] == "platform_id"
    assert data_pid["posted_platform_id"] == "dQw4w9WgXcQ"


def test_matching_strictly_by_url_or_platform_id_never_title() -> None:
    """Verifies that matching functions only accept URLs or platform IDs (PRD FR-11)."""
    assert extract_youtube_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    # Passing a video title does NOT match a YouTube video ID format
    title = "How to Learn Python Asyncio in 10 Minutes"
    # Even if title is passed, extract_youtube_video_id treats it as raw string, never resolving by title
    assert extract_youtube_video_id(title) == title


@pytest.mark.asyncio
async def test_analyst_skips_unlinked_posts_and_processes_after_linking(
    db_session: Session, client: TestClient
) -> None:
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Analytics for unlinked and linked drafts")
    run = create_run(db_session, goal_id=goal.id, run_type="post_mortem")

    draft = create_draft_version(
        db=db_session,
        lineage_id="lineage-unlinked-1",
        version=1,
        kind="script",
        platform="youtube",
        content="# Unlinked Video Script",
        created_by="model",
        status="APPROVED",
    )

    # 1. Mark as posted WITHOUT link (posted_ref == "none")
    res_mark = client.post(f"/api/v1/drafts/{draft.id}/mark-posted", json={}, headers=HEADERS)
    assert res_mark.status_code == 200
    assert res_mark.json()["posted_ref"] == "none"

    db_session.refresh(draft)
    assert draft.status == "POSTED"
    assert draft.posted_ref == "none"

    # Test db_load_metrics_tool for unlinked draft
    tool_res = db_load_metrics_tool(draft_id=draft.id, db=db_session)
    assert tool_res["unlinked"] is True
    assert "Automated metrics unavailable until linked" in tool_res["message"]
    assert tool_res["metrics"] == []

    # Run Analyst node while unlinked
    state: ContentState = {
        "run_id": run.id,
        "run_type": "post_mortem",
        "depth_level": "quick",
        "user_goal": "Check metrics",
        "creator_profile": {"creator_id": creator.id},
    }

    with patch("app.agents.analyst.request_analyst_llm", AsyncMock(side_effect=Exception("Model off"))):
        out_unlinked = await analyst_node(state, db_session=db_session)
        # Unlinked draft must be in unlinked_drafts and produce unlinked notice
        perf_insights = out_unlinked.get("performance_insights", {})
        assert draft.id in perf_insights.get("unlinked_drafts", [])
        unlinked_notes = perf_insights.get("unlinked_notes", [])
        assert any("Automated metrics unavailable until linked" in note for note in unlinked_notes)
        # No misleading metrics produced for unlinked draft
        findings_unlinked = [
            f for f in out_unlinked.get("analyst_findings", [])
            if f.get("draft_id") == draft.id
        ]
        assert len(findings_unlinked) == 0

    # 2. Now LINK the draft via POST /link-posted
    res_link = client.post(
        f"/api/v1/drafts/{draft.id}/link-posted",
        json={"posted_url": "https://youtube.com/watch?v=dQw4w9WgXcQ"},
        headers=HEADERS,
    )
    assert res_link.status_code == 200
    assert res_link.json()["posted_ref"] == "url"

    db_session.refresh(draft)
    assert draft.posted_ref == "url"
    assert draft.posted_url == "https://youtube.com/watch?v=dQw4w9WgXcQ"

    # Add metrics for this draft
    create_performance_metric(db_session, draft.id, "youtube", "views", 10000.0)
    create_performance_metric(db_session, draft.id, "youtube", "retention_30s", 72.0)

    # Test db_load_metrics_tool for linked draft
    tool_res_linked = db_load_metrics_tool(draft_id=draft.id, db=db_session)
    assert tool_res_linked["unlinked"] is False
    assert len(tool_res_linked["metrics"]) == 2

    # Run Analyst node after linking
    with patch("app.agents.analyst.request_analyst_llm", AsyncMock(side_effect=Exception("Model off"))):
        out_linked = await analyst_node(state, db_session=db_session)
        perf_insights_linked = out_linked.get("performance_insights", {})
        assert draft.id not in perf_insights_linked.get("unlinked_drafts", [])
        # Findings are now produced
        assert len(out_linked.get("analyst_findings", [])) >= 1
