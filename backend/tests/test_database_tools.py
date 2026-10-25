import os
import tempfile
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.repositories.creator import get_or_create_creator
from app.db.repositories.runs import create_goal, create_run
from app.tools.database_tools import (
    db_load_channel_insights_tool,
    db_load_latest_plan_tool,
    db_save_plan_tool,
    load_channel_insights,
    load_latest_draft,
    load_latest_plan,
    save_comment_insights,
    save_comments_batch,
    save_content_item,
    save_draft_version,
    save_plan_version,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_tools.db")
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()


def test_save_content_item_provenance(db_session: Session) -> None:
    """UT-32: Every result carries source, timestamp, platform/external_id."""
    creator = get_or_create_creator(db_session)
    res = save_content_item(
        creator_id=creator.id,
        platform="youtube",
        external_id="vid_test_01",
        owner_type="own",
        channel_external_id="UC_test_chan",
        title="Testing Content Item",
        db=db_session,
    )

    assert res["content_item_id"] is not None
    assert res["platform"] == "youtube"
    assert res["external_id"] == "vid_test_01"
    assert res["source"] == "database"
    assert "timestamp" in res


def test_save_comments_batch(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)
    item_res = save_content_item(
        creator_id=creator.id,
        platform="youtube",
        external_id="vid_test_02",
        owner_type="own",
        channel_external_id="UC_test_chan",
        title="Video With Comments",
        db=db_session,
    )
    item_id = item_res["content_item_id"]

    comments = [
        {"comment_id": "c1", "text": "Great video on SQLite WAL!", "likes": 10},
        {"comment_id": "c2", "text": "Very informative breakdown.", "likes": 5},
    ]

    res = save_comments_batch(item_id, comments, db=db_session)
    assert res["saved_count"] == 2
    assert res["source"] == "database"


def test_save_and_load_channel_insights(db_session: Session) -> None:
    """ADR-032 Channel rule & ADR-033 reference examples."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Analyze audience feedback")
    run = create_run(db_session, run_type="goal", depth_level="standard", goal_id=goal.id)

    # Save content item for channel A
    item_res = save_content_item(
        creator_id=creator.id,
        platform="youtube",
        external_id="vid_a",
        owner_type="own",
        channel_external_id="UC_chan_a",
        title="Chan A Video",
        db=db_session,
    )
    item_id = item_res["content_item_id"]

    save_comments_batch(
        item_id,
        [
            {"comment_id": "c_a1", "text": "Love FastAPI and SQLite WAL", "likes": 12},
            {"comment_id": "c_a2", "text": "How do you handle migrations?", "likes": 4},
        ],
        db=db_session,
    )

    # Save comment insights for channel A
    themes = [
        {
            "theme_label": "FastAPI & SQLite WAL",
            "comment_count": 2,
            "coverage_analyzed": 2,
            "coverage_total": 2,
            "example_comment_ids": ["c_a1", "c_a2"],
        }
    ]
    save_res = save_comment_insights(
        creator_id=creator.id,
        run_id=run.id,
        themes=themes,
        source_content_item_ids=[item_id],
        db=db_session,
    )
    assert save_res["count"] == 1

    # Load for channel A -> must find it
    loaded_a = load_channel_insights("UC_chan_a", db=db_session)
    assert len(loaded_a["insights"]) == 1
    ins = loaded_a["insights"][0]
    assert ins["theme_label"] == "FastAPI & SQLite WAL"
    assert len(ins["examples"]) == 2

    # Load for channel B -> excluded under ADR-032 channel rule
    loaded_b = load_channel_insights("UC_chan_b", db=db_session)
    assert len(loaded_b["insights"]) == 0


def test_save_and_load_plan_version(db_session: Session) -> None:
    """ADR-029 & VER-01: Plan lineage and immutable versions."""
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Plan content")
    run = create_run(db_session, run_type="goal", depth_level="standard", goal_id=goal.id)

    items_v1 = [
        {
            "topic": "FastAPI with LangGraph",
            "format": "long_form",
            "platform": "youtube",
            "objective": "Teach agentic patterns",
            "reason": "Audience request from comments",
            "priority": 1,
        }
    ]

    res_v1 = save_plan_version(
        lineage_id="lin_plan_001",
        version=1,
        run_id=run.id,
        items=items_v1,
        db=db_session,
    )
    assert res_v1["version"] == 1
    assert res_v1["status"] == "DRAFT"

    # Version 2
    items_v2 = [
        items_v1[0],
        {
            "topic": "SQLite Concurrency in Python",
            "format": "short",
            "platform": "youtube",
            "objective": "Explain WAL mode and busy timeout",
            "reason": "High interest topic",
            "priority": 2,
        },
    ]
    res_v2 = save_plan_version(
        lineage_id="lin_plan_001",
        version=2,
        run_id=run.id,
        items=items_v2,
        previous_version_id=res_v1["plan_id"],
        db=db_session,
    )
    assert res_v2["version"] == 2

    # Load latest plan
    latest = load_latest_plan("lin_plan_001", db=db_session)
    assert latest["plan"] is not None
    assert latest["plan"]["version"] == 2
    assert len(latest["plan"]["items"]) == 2


def test_save_and_load_draft_version(db_session: Session) -> None:
    """VER-02: Draft versioning and lineage."""
    res_d1 = save_draft_version(
        lineage_id="lin_draft_001",
        version=1,
        kind="script",
        platform="youtube",
        content="Intro: Welcome to this video on LangGraph.",
        db=db_session,
    )
    assert res_d1["version"] == 1
    assert res_d1["status"] == "WRITING"

    latest = load_latest_draft("lin_draft_001", db=db_session)
    assert latest["draft"] is not None
    assert latest["draft"]["content"] == "Intro: Welcome to this video on LangGraph."


def test_langchain_tool_wrappers() -> None:
    """Tool invocation for ReAct agents."""
    # Test tool metadata
    assert db_load_channel_insights_tool.name == "db_load_channel_insights_tool"
    assert db_save_plan_tool.name == "db_save_plan_tool"
    assert db_load_latest_plan_tool.name == "db_load_latest_plan_tool"
