import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import (
    Approval,
    Comment,
    CommentInsight,
    CommentInsightExample,
    CommentInsightSource,
    ContentItem,
    ContentPlan,
    Creator,
    Run,
    Setting,
)


@pytest.fixture
def db_session() -> Session:
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Enable SQLite foreign keys on test engine
    from sqlalchemy import event

    @event.listens_for(test_engine, "connect")
    def do_connect(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(test_engine)


def test_creator_and_settings_creation(db_session: Session) -> None:
    creator = Creator(
        display_name="Tech Creator",
        audience_level="intermediate",
        youtube_channel_id="UC_12345",
        youtube_channel_handle="@techcreator",
        youtube_channel_title="Tech Creator Channel",
        youtube_channel_verified=True,
    )
    db_session.add(creator)
    db_session.commit()

    setting = Setting(
        key="niche",
        value_json={"niche": "FastAPI & AI Systems"},
    )
    db_session.add(setting)
    db_session.commit()

    saved_creator = db_session.query(Creator).filter_by(id=creator.id).first()
    assert saved_creator is not None
    assert saved_creator.youtube_channel_handle == "@techcreator"
    assert saved_creator.youtube_channel_verified is True

    saved_setting = db_session.query(Setting).filter_by(key="niche").first()
    assert saved_setting is not None
    assert saved_setting.value_json["niche"] == "FastAPI & AI Systems"


def test_run_status_interrupted_allowed(db_session: Session) -> None:
    creator = Creator(display_name="Creator")
    db_session.add(creator)
    db_session.commit()

    run = Run(
        run_type="goal",
        depth_level="standard",
        status="INTERRUPTED",
        degraded=True,
        degraded_reason="Ollama connection timeout during Supervisor routing",
    )
    db_session.add(run)
    db_session.commit()

    saved_run = db_session.query(Run).filter_by(id=run.id).first()
    assert saved_run is not None
    assert saved_run.status == "INTERRUPTED"
    assert saved_run.degraded is True


def test_run_invalid_status_rejected(db_session: Session) -> None:
    run = Run(
        run_type="goal",
        depth_level="standard",
        status="INVALID_STATUS_NAME",
    )
    db_session.add(run)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_comments_nullable_text_and_retention(db_session: Session) -> None:
    creator = Creator(display_name="Creator")
    db_session.add(creator)
    db_session.commit()

    item = ContentItem(
        creator_id=creator.id,
        platform="youtube",
        external_id="vid_123",
        owner_type="own",
        channel_external_id="UC_12345",
        title="Test Video",
        published_at=creator.created_at,
    )
    db_session.add(item)
    db_session.commit()

    # Active comment with text
    comment = Comment(
        content_item_id=item.id,
        external_id="c_123",
        text="Great video on FastAPI!",
        like_count=5,
        published_at=creator.created_at,
    )
    db_session.add(comment)
    db_session.commit()

    # After 90 days retention, text is cleared to None while row remains
    comment.text = None
    db_session.commit()

    updated_comment = db_session.query(Comment).filter_by(id=comment.id).first()
    assert updated_comment is not None
    assert updated_comment.text is None
    assert updated_comment.like_count == 5


def test_comment_insight_sources_and_examples(db_session: Session) -> None:
    creator = Creator(display_name="Creator")
    db_session.add(creator)
    db_session.commit()

    run = Run(status="COMPLETED")
    db_session.add(run)
    db_session.commit()

    item = ContentItem(
        creator_id=creator.id,
        platform="youtube",
        external_id="vid_123",
        owner_type="own",
        channel_external_id="UC_12345",
        title="Test Video",
        published_at=creator.created_at,
    )
    db_session.add(item)
    db_session.commit()

    comment = Comment(
        content_item_id=item.id,
        external_id="c_123",
        text="How to do async worker queues?",
        published_at=creator.created_at,
    )
    db_session.add(comment)
    db_session.commit()

    insight = CommentInsight(
        creator_id=creator.id,
        run_id=run.id,
        theme_label="Background Workers",
        comment_count=1,
    )
    db_session.add(insight)
    db_session.commit()

    # Link source and example
    source = CommentInsightSource(insight_id=insight.id, content_item_id=item.id)
    example = CommentInsightExample(insight_id=insight.id, comment_id=comment.id)
    db_session.add_all([source, example])
    db_session.commit()

    saved_insight = db_session.query(CommentInsight).filter_by(id=insight.id).first()
    assert saved_insight is not None
    assert len(saved_insight.sources) == 1
    assert saved_insight.sources[0].content_item_id == item.id
    assert len(saved_insight.examples) == 1
    assert saved_insight.examples[0].comment_id == comment.id


def test_plan_and_draft_versioning_constraints(db_session: Session) -> None:
    creator = Creator(display_name="Creator")
    db_session.add(creator)
    db_session.commit()

    run = Run(status="RUNNING")
    db_session.add(run)
    db_session.commit()

    lineage_id = "lin_plan_001"
    plan_v1 = ContentPlan(
        lineage_id=lineage_id,
        version=1,
        run_id=run.id,
        status="DRAFT",
    )
    db_session.add(plan_v1)
    db_session.commit()

    plan_v2 = ContentPlan(
        lineage_id=lineage_id,
        version=2,
        previous_version_id=plan_v1.id,
        run_id=run.id,
        status="PENDING_APPROVAL",
    )
    db_session.add(plan_v2)
    db_session.commit()

    # Attempt duplicate (lineage_id, version) must fail unique constraint
    duplicate_plan = ContentPlan(
        lineage_id=lineage_id,
        version=1,
        run_id=run.id,
        status="DRAFT",
    )
    db_session.add(duplicate_plan)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_approval_lifecycle_and_exact_item_id(db_session: Session) -> None:
    creator = Creator(display_name="Creator")
    db_session.add(creator)
    db_session.commit()

    run = Run(status="WAITING_APPROVAL")
    db_session.add(run)
    db_session.commit()

    plan = ContentPlan(
        run_id=run.id,
        status="PENDING_APPROVAL",
    )
    db_session.add(plan)
    db_session.commit()

    approval = Approval(
        run_id=run.id,
        item_type="plan",
        item_id=plan.id,
        status="PENDING",
    )
    db_session.add(approval)
    db_session.commit()

    saved_approval = db_session.query(Approval).filter_by(id=approval.id).first()
    assert saved_approval is not None
    assert saved_approval.item_id == plan.id
    assert saved_approval.status == "PENDING"
