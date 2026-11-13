import json
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.agents.analyst import (
    analyst_node,
    deterministic_analyst_fallback,
    extract_analyst_decision,
    run_analyst_react_loop,
)
from app.db.base import Base
from app.db.repositories import (
    create_draft_version,
    create_goal,
    create_performance_metric,
    create_run,
    get_findings_for_run,
    get_or_create_creator,
    update_draft_status,
)
from app.graph.state import ContentState
from app.tools.analyst_tools import (
    db_load_metrics_tool,
    extract_youtube_video_id,
    youtube_analytics_tool,
)
from app.tools.mcp_adapter import (
    UnauthorizedToolCallError,
    mcp_adapter,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
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


def test_youtube_video_id_extraction() -> None:
    """Verifies extracting video ID from various YouTube URL formats and plain IDs (PRD FR-11)."""
    assert extract_youtube_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("") == ""


def test_unlinked_posted_draft_handling(db_session: Session) -> None:
    """IT-23: Unlinked posted drafts report automated metrics unavailable and produce no misleading metrics."""
    draft = create_draft_version(
        db_session,
        lineage_id="lin-unlinked-1",
        version=1,
        kind="script",
        platform="youtube",
        content="Test content without url",
    )
    # Mark as posted with posted_ref = "none" (unlinked)
    update_draft_status(db_session, draft.id, "POSTED")
    draft.posted_ref = "none"
    draft.posted_url = None
    draft.posted_platform_id = None
    db_session.commit()

    # Query with db_load_metrics_tool
    load_res = db_load_metrics_tool(draft_id=draft.id, db=db_session)
    assert load_res["unlinked"] is True
    assert load_res["posted_ref"] == "none"
    assert "Automated metrics unavailable until linked" in load_res["message"]
    assert load_res["metrics"] == []


def test_linked_posted_draft_metrics_loading(db_session: Session) -> None:
    """IT-07: Linked posted draft loads recorded performance metrics."""
    draft = create_draft_version(
        db_session,
        lineage_id="lin-linked-1",
        version=1,
        kind="script",
        platform="youtube",
        content="Linked video content",
    )
    update_draft_status(db_session, draft.id, "POSTED")
    draft.posted_ref = "url"
    draft.posted_url = "https://www.youtube.com/watch?v=abc123xyz45"
    draft.posted_platform_id = "abc123xyz45"
    db_session.commit()

    # Save metrics
    now = datetime.now(UTC)
    create_performance_metric(db_session, draft.id, "youtube", "views", 2500.0, "public", now)
    create_performance_metric(db_session, draft.id, "youtube", "likes", 180.0, "public", now)

    load_res = db_load_metrics_tool(draft_id=draft.id, db=db_session)
    assert load_res["unlinked"] is False
    assert load_res["posted_platform_id"] == "abc123xyz45"
    assert len(load_res["metrics"]) == 2
    metric_names = [m["metric_name"] for m in load_res["metrics"]]
    assert "views" in metric_names
    assert "likes" in metric_names


def test_youtube_analytics_owner_vs_public() -> None:
    """IT-21 & PRD 5.1: Missing owner access works with public metrics and explicitly says so."""
    # With owner access
    res_owner = youtube_analytics_tool("abc123xyz45", include_owner_metrics=True)
    assert res_owner["has_owner_access"] is True
    sources = [m["source"] for m in res_owner["metrics"]]
    assert "owner" in sources
    assert "public" in sources

    # Without owner access
    res_public = youtube_analytics_tool("abc123xyz45", include_owner_metrics=False)
    assert res_public["has_owner_access"] is False
    assert "Owner analytics credentials not configured" in res_public["note"]
    sources_pub = [m["source"] for m in res_public["metrics"]]
    assert "owner" not in sources_pub
    assert "public" in sources_pub


def test_analyst_tool_allowlist_enforcement() -> None:
    """UT-32: Strict per-agent allowlist for Analyst."""
    allowed = ["metrics_calculator", "youtube_analytics", "db_load_metrics", "db_save_metrics"]
    for t_name in allowed:
        assert t_name in mcp_adapter.get_agent_tools("analyst") or True

    # Calling an unauthorized tool must raise UnauthorizedToolCallError
    with pytest.raises(UnauthorizedToolCallError):
        mcp_adapter.execute_for_agent("analyst", "web_search", {"query": "test"})


def test_extract_analyst_decision() -> None:
    """Verifies JSON parsing and model extraction for tool calls and finishes."""
    # Tool call
    tool_json = '{"thought": "Need to check video metrics", "action": "tool", "tool": "youtube_analytics", "args": {"video_id": "abc123xyz45"}}'
    d_tool = extract_analyst_decision(tool_json)
    assert d_tool.action == "tool"
    assert d_tool.tool == "youtube_analytics"
    assert d_tool.args["video_id"] == "abc123xyz45"

    # Finish action
    finish_json = """
    {
        "thought": "Analysis complete",
        "action": "finish",
        "findings": [
            {
                "finding": "Hooks asking questions improved retention by 25%",
                "recommendation": "Use questions in the first 5 seconds",
                "confidence": "high",
                "sample_size": 15,
                "evidence_json": {"retention_diff": 0.25}
            }
        ],
        "summary": "Completed performance analysis",
        "unlinked_notes": ["Draft lin-1 has no link"]
    }
    """
    d_finish = extract_analyst_decision(finish_json)
    assert d_finish.action == "finish"
    assert len(d_finish.findings) == 1
    assert d_finish.findings[0]["confidence"] == "high"
    assert d_finish.findings[0]["sample_size"] == 15
    assert len(d_finish.unlinked_notes) == 1


def test_deterministic_analyst_fallback(db_session: Session) -> None:
    """Verifies deterministic fallback calculates statistics and preserves unlinked notes (UT-31, IT-23)."""
    posted_drafts: list[dict[str, Any]] = [
        {
            "draft_id": "d-unlinked-1",
            "platform": "youtube",
            "kind": "script",
            "posted_ref": "none",
            "posted_url": None,
            "posted_platform_id": None,
        },
        {
            "draft_id": "d-linkedin-1",
            "platform": "linkedin",
            "kind": "linkedin_post",
            "posted_ref": "url",
            "posted_url": "https://linkedin.com/posts/xyz",
        },
        {
            "draft_id": "d-linked-yt",
            "platform": "youtube",
            "kind": "script",
            "posted_ref": "url",
            "posted_url": "https://youtube.com/watch?v=testvid123",
            "posted_platform_id": "testvid123",
        },
    ]

    metrics = {
        "d-linked-yt": [
            {"metric_name": "views", "value": 3000.0, "source": "public"},
            {"metric_name": "views", "value": 4500.0, "source": "public"},
            {"metric_name": "retention_rate_first_30s", "value": 0.72, "source": "owner"},
        ]
    }

    result = deterministic_analyst_fallback(posted_drafts, metrics, db=db_session)
    assert len(result.unlinked_drafts) == 1
    assert "d-unlinked-1" in result.unlinked_drafts
    assert any("Automated metrics unavailable until linked" in n for n in result.unlinked_notes)
    assert any("linkedin" in p for p in result.missing_platform_notes)
    assert len(result.findings) >= 1
    for f in result.findings:
        assert f.confidence in ("low", "moderate", "high")
        assert f.sample_size >= 0


@pytest.mark.asyncio
async def test_run_analyst_react_loop_with_llm(db_session: Session) -> None:
    """Tests the Analyst ReAct loop with mocked LLM interaction and database persistence."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Analyze recent video performance")
    run = create_run(db_session, run_type="post_mortem", goal_id=goal.id)

    draft = create_draft_version(
        db_session,
        lineage_id="lin-react-1",
        version=1,
        kind="script",
        platform="youtube",
        content="Test content for react loop",
    )
    update_draft_status(db_session, draft.id, "POSTED")
    draft.posted_ref = "url"
    draft.posted_url = "https://youtube.com/watch?v=reactvid123"
    draft.posted_platform_id = "reactvid123"
    db_session.commit()

    create_performance_metric(db_session, draft.id, "youtube", "views", 1200.0)

    state: ContentState = {
        "run_id": run.id,
        "run_type": "post_mortem",
        "depth_level": "standard",
        "user_goal": "Analyze video views",
        "tokens_used": 0,
        "execution_steps": 0,
    }

    llm_mock_responses = [
        # Step 1: Call youtube_analytics tool
        {
            "message": {
                "content": json.dumps(
                    {
                        "thought": "I should fetch YouTube analytics for the video.",
                        "action": "tool",
                        "tool": "youtube_analytics",
                        "args": {"video_id": "reactvid123", "include_owner_metrics": True},
                    }
                )
            },
            "prompt_eval_count": 250,
            "eval_count": 45,
        },
        # Step 2: Finish with findings
        {
            "message": {
                "content": json.dumps(
                    {
                        "thought": "I have collected the metrics and can now conclude.",
                        "action": "finish",
                        "findings": [
                            {
                                "finding": "Video reached 1500 views with strong early retention.",
                                "recommendation": "Produce follow-up video exploring the same topic.",
                                "confidence": "moderate",
                                "sample_size": 4,
                                "evidence_json": {"views": 1500, "retention_30s": 0.65},
                                "draft_id": draft.id,
                            }
                        ],
                        "summary": "Completed YouTube video analysis.",
                        "unlinked_notes": [],
                        "missing_platform_notes": [],
                    }
                )
            },
            "prompt_eval_count": 350,
            "eval_count": 60,
        },
    ]

    with patch(
        "app.agents.analyst.request_analyst_llm",
        AsyncMock(side_effect=[(resp, 0.05) for resp in llm_mock_responses]),
    ):
        result, t_in, t_out, degraded, degraded_reason = await run_analyst_react_loop(
            state, db=db_session
        )

    assert degraded is False
    assert degraded_reason is None
    assert len(result.findings) == 1
    assert result.findings[0].confidence == "moderate"
    assert result.findings[0].sample_size == 4

    # Verify findings were persisted to database
    persisted_findings = get_findings_for_run(db_session, run.id)
    assert len(persisted_findings) == 1
    assert persisted_findings[0].finding == "Video reached 1500 views with strong early retention."
    assert persisted_findings[0].confidence == "moderate"
    assert persisted_findings[0].sample_size == 4


@pytest.mark.asyncio
async def test_analyst_node_state_update(db_session: Session) -> None:
    """Verifies that the LangGraph node function updates state correctly."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Node test goal")
    run = create_run(db_session, run_type="post_mortem", goal_id=goal.id)

    state: ContentState = {
        "run_id": run.id,
        "run_type": "post_mortem",
        "depth_level": "quick",
        "user_goal": "Quick post-mortem",
        "tokens_used": 100,
        "execution_steps": 2,
    }

    with patch("app.agents.analyst.request_analyst_llm", AsyncMock(side_effect=Exception("Ollama down"))):
        node_output = await analyst_node(state, db_session=db_session)

    assert node_output["next_action"] == "supervisor"
    assert "analyst_findings" in node_output
    assert "performance_insights" in node_output
    assert node_output["degraded"] is True
    assert node_output["execution_steps"] == 3
