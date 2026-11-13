"""Phase 4 Comprehensive Integration and Acceptance Verification (TEST-04).

Covers all Phase 4 specifications from TEST_PLAN.md:
- IT-07: Mark as posted (only approved drafts can be marked; Analyst can then process them)
- IT-08: Findings change the plan (after stored findings, next plan reflects them and records reasons)
- IT-21: Missing platform access (LinkedIn and X give no performance data and say so; YouTube owner metrics fallback)
- IT-23: Unlinked posted draft (reports automated metrics unavailable, produces no misleading metrics; processed after linking)
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.analyst import analyst_node
from app.agents.strategist import strategist_node
from app.config import settings
from app.db.base import Base
from app.db.models import ContentPlan
from app.db.repositories.analytics import (
    create_analyst_finding,
    create_or_update_strategy_entry,
    create_performance_metric,
    get_active_strategy_entries,
    get_active_strategy_entry,
    get_strategy_history,
)
from app.db.repositories.creator import get_or_create_creator
from app.db.repositories.plans import (
    create_draft_version,
)
from app.db.repositories.runs import create_goal, create_run
from app.db.session import get_db
from app.graph.builder import create_content_graph
from app.graph.state import ContentState
from app.graph.supervisor import calculate_eligible_nodes
from app.main import app as fastapi_app
from app.tools.analyst_tools import db_load_metrics_tool, youtube_analytics_tool

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


@pytest.mark.asyncio
async def test_it_07_mark_as_posted_allows_analyst_processing(
    db_session: Session, client: TestClient
) -> None:
    """IT-07: Only approved drafts can be marked, and the Analyst can then process them."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Test IT-07 Mark as Posted")
    run = create_run(db_session, goal_id=goal.id, run_type="post_mortem")

    # Draft in WRITING state cannot be marked posted
    draft_writing = create_draft_version(
        db=db_session,
        lineage_id="lineage-it07-1",
        version=1,
        kind="script",
        platform="youtube",
        content="# Hook\nInitial draft",
        status="WRITING",
    )

    res_fail = client.post(f"/api/v1/drafts/{draft_writing.id}/mark-posted", json={}, headers=HEADERS)
    assert res_fail.status_code == 409
    assert res_fail.json()["error"]["code"] == "NOT_APPROVED"

    # Draft in APPROVED state can be marked posted
    draft_approved = create_draft_version(
        db=db_session,
        lineage_id="lineage-it07-2",
        version=1,
        kind="script",
        platform="youtube",
        content="# Hook\nApproved script",
        status="APPROVED",
    )

    res_ok = client.post(
        f"/api/v1/drafts/{draft_approved.id}/mark-posted",
        json={"posted_url": "https://youtube.com/watch?v=it07vid1234"},
        headers=HEADERS,
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "POSTED"
    assert res_ok.json()["analytics_eligible"] is True

    # Refresh draft instance
    db_session.refresh(draft_approved)
    create_performance_metric(db_session, draft_approved.id, "youtube", "views", 8500.0)

    # Analyst processes posted draft
    state: ContentState = {
        "run_id": run.id,
        "run_type": "post_mortem",
        "depth_level": "quick",
        "user_goal": "Post-mortem analysis",
        "creator_profile": {"creator_id": creator.id},
    }

    with patch("app.agents.analyst.request_analyst_llm", AsyncMock(side_effect=Exception("Model off"))):
        out = await analyst_node(state, db_session=db_session)
        assert len(out["analyst_findings"]) >= 1
        finding = out["analyst_findings"][0]
        assert finding["confidence"] in ("low", "moderate", "high")


@pytest.mark.asyncio
async def test_it_08_findings_change_next_plan_and_record_reason(
    db_session: Session,
) -> None:
    """IT-08: After a stored finding, the next plan reflects it and records the reason."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Content planning after retention post-mortem")
    run = create_run(db_session, goal_id=goal.id)

    # Store an analyst finding from prior analysis
    f1 = create_analyst_finding(
        db=db_session,
        run_id=run.id,
        finding="Hook duration under 15s increases viewer retention by 38%",
        recommendation="Limit tutorial video hooks to 15 seconds max",
        confidence="high",
        sample_size=14,
        evidence_json={"avg_retention_lift": 38.0, "threshold_s": 15},
    )

    # Store initial strategy entry
    strat1 = create_or_update_strategy_entry(
        db=db_session,
        creator_id=creator.id,
        key="preferred_hook_duration",
        value_json={"max_seconds": 15},
        reason="Empirical finding shows 38% retention lift for hooks under 15s",
        supporting_finding_ids_json=[f1.id],
    )
    assert strat1.status == "active"

    state: ContentState = {
        "run_id": run.id,
        "run_type": "goal",
        "depth_level": "standard",
        "user_goal": "Create a 3-part video series on FastAPI and SQLite",
        "creator_profile": {"creator_id": creator.id, "niche": "Python Dev"},
        "analyst_findings": [
            {
                "id": f1.id,
                "finding": f1.finding,
                "recommendation": f1.recommendation,
                "confidence": f1.confidence,
                "sample_size": f1.sample_size,
            }
        ],
    }

    with patch("app.agents.strategist.request_strategist_llm", AsyncMock(side_effect=Exception("Model off"))):
        out = await strategist_node(state, db_session=db_session)
        assert out["approval_status"] == "PENDING"
        plan_id = out["current_plan_id"]
        assert plan_id is not None

        plan = db_session.query(ContentPlan).filter_by(id=plan_id).first()
        assert plan is not None
        assert len(plan.items) >= 1

        # Plan items must reflect analyst findings and state the reason (IT-08)
        found_empirical_reason = any(
            "Empirical finding" in (it.reason or "") or "Hook duration" in (it.reason or "")
            for it in plan.items
        )
        assert found_empirical_reason is True

    # Now verify successive findings supersede strategy entry lineage
    f2 = create_analyst_finding(
        db=db_session,
        run_id=run.id,
        finding="Ultra-concise hooks under 8s improve retention further by 12%",
        recommendation="Reduce tutorial video hooks to 8 seconds max",
        confidence="high",
        sample_size=20,
    )

    strat2 = create_or_update_strategy_entry(
        db=db_session,
        creator_id=creator.id,
        key="preferred_hook_duration",
        value_json={"max_seconds": 8},
        reason="Updated finding: 8s hooks yield an additional 12% retention",
        supporting_finding_ids_json=[f2.id],
    )

    active_entry = get_active_strategy_entry(db_session, creator.id, "preferred_hook_duration")
    assert active_entry is not None
    assert active_entry.id == strat2.id
    assert active_entry.value_json["max_seconds"] == 8

    # Old entry is superseded
    db_session.refresh(strat1)
    assert strat1.status == "superseded"

    history = get_strategy_history(db_session, creator.id, key="preferred_hook_duration")
    assert len(history) == 2


def test_it_21_platform_capabilities_and_access(db_session: Session) -> None:
    """IT-21: Missing platform access gives partial result; LinkedIn and X give no performance data and say so."""
    # 1. LinkedIn & X capability handling:
    posted_drafts = [
        {"draft_id": "d-li", "platform": "linkedin", "posted_ref": "url", "posted_url": "https://linkedin.com/posts/1"},
        {"draft_id": "d-x", "platform": "x", "posted_ref": "url", "posted_url": "https://x.com/post/1"},
    ]
    # Check deterministic fallback handling
    from app.agents.analyst import deterministic_analyst_fallback

    res = deterministic_analyst_fallback(posted_drafts=posted_drafts, collected_metrics={}, db=db_session)
    # Must report that LinkedIn and X have no performance data available in v1
    assert any("Platform 'linkedin': No performance data available in v1" in n for n in res.missing_platform_notes)
    assert any("Platform 'x': No performance data available in v1" in n for n in res.missing_platform_notes)
    # Zero misleading metrics produced for LinkedIn/X
    assert all(f.draft_id not in ("d-li", "d-x") for f in res.findings)

    # 2. YouTube Owner vs Public metrics fallback (PRD 5.1):
    # With owner access:
    owner_res = youtube_analytics_tool("dQw4w9WgXcQ", include_owner_metrics=True)
    metric_names_owner = {m["metric_name"] for m in owner_res["metrics"]}
    assert "avg_view_duration_seconds" in metric_names_owner

    # Without owner access (unconfigured credentials): returns public metrics only and says so
    public_res = youtube_analytics_tool("dQw4w9WgXcQ", include_owner_metrics=False)
    metric_names_pub = {m["metric_name"] for m in public_res["metrics"]}
    assert "views" in metric_names_pub
    assert "average_view_percentage" not in metric_names_pub
    assert "Owner analytics credentials not configured" in public_res["note"]


@pytest.mark.asyncio
async def test_it_23_unlinked_posted_draft_produces_no_misleading_analytics(
    db_session: Session, client: TestClient
) -> None:
    """IT-23: Unlinked draft reports automated metrics unavailable; after linking, draft is processed."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "IT-23 Unlinked Verification")
    run = create_run(db_session, goal_id=goal.id, run_type="post_mortem")

    draft = create_draft_version(
        db=db_session,
        lineage_id="lineage-it23-1",
        version=1,
        kind="script",
        platform="youtube",
        content="# Hook\nUnlinked Video",
        status="APPROVED",
    )

    # 1. Mark as posted without a link
    res_mark = client.post(f"/api/v1/drafts/{draft.id}/mark-posted", json={}, headers=HEADERS)
    assert res_mark.status_code == 200
    assert res_mark.json()["posted_ref"] == "none"

    db_session.refresh(draft)

    # Tool explicitly reports unavailable
    tool_check = db_load_metrics_tool(draft_id=draft.id, db=db_session)
    assert tool_check["unlinked"] is True
    assert "Automated metrics unavailable until linked" in tool_check["message"]

    # Analyst run produces no misleading metrics
    state: ContentState = {
        "run_id": run.id,
        "run_type": "post_mortem",
        "depth_level": "quick",
        "user_goal": "Post-mortem analysis on unlinked post",
        "creator_profile": {"creator_id": creator.id},
    }

    with patch("app.agents.analyst.request_analyst_llm", AsyncMock(side_effect=Exception("Model off"))):
        out_unlinked = await analyst_node(state, db_session=db_session)
        perf_insights = out_unlinked.get("performance_insights", {})
        assert draft.id in perf_insights.get("unlinked_drafts", [])
        assert any("Automated metrics unavailable until linked" in n for n in perf_insights.get("unlinked_notes", []))
        # Ensure no misleading metrics
        assert len(out_unlinked["analyst_findings"]) == 0

    # 2. Attach link via POST /drafts/{id}/link-posted
    res_link = client.post(
        f"/api/v1/drafts/{draft.id}/link-posted",
        json={"posted_url": "https://youtube.com/watch?v=it23vid123"},
        headers=HEADERS,
    )
    assert res_link.status_code == 200
    assert res_link.json()["posted_ref"] == "url"

    db_session.refresh(draft)
    create_performance_metric(db_session, draft.id, "youtube", "views", 12000.0)

    # Analyst run now processes the draft
    with patch("app.agents.analyst.request_analyst_llm", AsyncMock(side_effect=Exception("Model off"))):
        out_linked = await analyst_node(state, db_session=db_session)
        perf_insights_linked = out_linked.get("performance_insights", {})
        assert draft.id not in perf_insights_linked.get("unlinked_drafts", [])
        assert len(out_linked["analyst_findings"]) >= 1


@pytest.mark.asyncio
async def test_closed_loop_feedback_end_to_end(db_session: Session) -> None:
    """End-to-end feedback loop: Analyst -> findings -> Supervisor -> Strategist -> plan with reasons."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Closed-loop feedback test")
    run = create_run(db_session, goal_id=goal.id, run_type="post_mortem")

    draft = create_draft_version(
        db=db_session,
        lineage_id="lineage-loop-1",
        version=1,
        kind="script",
        platform="youtube",
        content="# Hook\nLoop Script",
        status="POSTED",
    )
    draft.posted_ref = "url"
    draft.posted_url = "https://youtube.com/watch?v=loopvid1"
    draft.posted_platform_id = "loopvid1"
    db_session.commit()

    create_performance_metric(db_session, draft.id, "youtube", "views", 15000.0)
    create_performance_metric(db_session, draft.id, "youtube", "retention_30s", 75.0)

    _ = create_content_graph(db_session=db_session)

    initial_state: ContentState = {
        "run_id": run.id,
        "run_type": "post_mortem",
        "depth_level": "standard",
        "user_goal": "Post-mortem analysis on YouTube tutorial performance",
        "creator_profile": {"creator_id": creator.id, "niche": "Python Programming"},
        "has_new_posts": True,
        "new_posts_count": 1,
        "tokens_used": 0,
        "execution_steps": 0,
    }

    with (
        patch("app.agents.analyst.request_analyst_llm", AsyncMock(side_effect=Exception("Model off"))),
        patch("app.agents.strategist.request_strategist_llm", AsyncMock(side_effect=Exception("Model off"))),
    ):
        # 1. Analyst executes
        analyst_out = await analyst_node(initial_state, db_session=db_session)
        assert len(analyst_out["analyst_findings"]) >= 1

        # 2. Update state with findings
        initial_state.update(analyst_out)  # type: ignore[typeddict-item]

        # 3. Supervisor routes to strategist
        next_nodes = calculate_eligible_nodes(initial_state)
        assert "strategist" in next_nodes

        # 4. Strategist incorporates findings into new content plan
        strategist_out = await strategist_node(initial_state, db_session=db_session)
        assert strategist_out["approval_status"] == "PENDING"
        assert strategist_out["current_plan_id"] is not None

        # Verify strategy entries recorded in database
        entries = get_active_strategy_entries(db_session, creator.id)
        assert len(entries) >= 1
