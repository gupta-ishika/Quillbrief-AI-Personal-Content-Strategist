from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import AnalystFinding, PerformanceMetric, StrategyEntry
from app.db.repositories import (
    create_analyst_finding,
    create_draft_version,
    create_goal,
    create_or_update_strategy_entry,
    create_performance_metric,
    create_run,
    get_active_strategy_entries,
    get_active_strategy_entry,
    get_all_findings,
    get_findings_for_draft,
    get_findings_for_run,
    get_metrics_by_platform,
    get_metrics_for_draft,
    get_or_create_creator,
    get_strategy_history,
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


def test_performance_metrics_crud_and_constraints(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Test goal")
    create_run(db_session, goal_id=goal.id)
    draft = create_draft_version(
        db_session,
        lineage_id="lineage-1",
        version=1,
        kind="script",
        platform="youtube",
        content="Test content",
    )

    # 1. Create metrics
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
    m1 = create_performance_metric(
        db_session,
        draft_id=draft.id,
        platform="youtube",
        metric_name="views",
        value=1500.0,
        source="public",
        collected_at=now,
    )
    assert m1.id is not None
    assert m1.value == 1500.0

    m2 = create_performance_metric(
        db_session,
        draft_id=draft.id,
        platform="youtube",
        metric_name="avg_view_duration",
        value=240.5,
        source="owner",
        collected_at=now,
    )
    assert m2.source == "owner"

    # 2. Query metrics
    draft_metrics = get_metrics_for_draft(db_session, draft.id)
    assert len(draft_metrics) == 2

    yt_metrics = get_metrics_by_platform(db_session, "youtube")
    assert len(yt_metrics) == 2

    # 3. Check constraint on source (only 'public', 'owner')
    with pytest.raises(IntegrityError):
        invalid_metric = PerformanceMetric(
            draft_id=draft.id,
            platform="youtube",
            metric_name="shares",
            value=10.0,
            source="unknown_source",
            collected_at=datetime.now(UTC),
        )
        db_session.add(invalid_metric)
        db_session.commit()
    db_session.rollback()

    # 4. Unique constraint on (draft_id, metric_name, collected_at)
    with pytest.raises(IntegrityError):
        dup_metric = PerformanceMetric(
            draft_id=draft.id,
            platform="youtube",
            metric_name="views",
            value=2000.0,
            source="public",
            collected_at=now,
        )
        db_session.add(dup_metric)
        db_session.commit()
    db_session.rollback()

    # 5. Relationship and Cascade delete on draft
    assert len(draft.performance_metrics) == 2
    db_session.delete(draft)
    db_session.commit()
    assert len(get_metrics_for_draft(db_session, draft.id)) == 0


def test_analyst_findings_crud_and_constraints(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)
    goal = create_goal(db_session, creator.id, "Test goal")
    run = create_run(db_session, goal_id=goal.id)
    draft = create_draft_version(
        db_session,
        lineage_id="lineage-1",
        version=1,
        kind="script",
        platform="youtube",
        content="Test content",
    )

    # 1. Create finding
    finding = create_analyst_finding(
        db_session,
        run_id=run.id,
        finding="Videos with direct hook have 35% higher retention",
        recommendation="Use direct questions in first 5 seconds",
        confidence="high",
        sample_size=12,
        evidence_json={"retention_first_30s": 0.65},
        draft_id=draft.id,
    )
    assert finding.id is not None
    assert finding.confidence == "high"
    assert finding.sample_size == 12

    # 2. Query findings
    run_findings = get_findings_for_run(db_session, run.id)
    assert len(run_findings) == 1
    assert run_findings[0].id == finding.id

    draft_findings = get_findings_for_draft(db_session, draft.id)
    assert len(draft_findings) == 1

    all_findings = get_all_findings(db_session)
    assert len(all_findings) == 1

    # 3. Check constraint on confidence (only 'low', 'moderate', 'high')
    with pytest.raises(IntegrityError):
        invalid_finding = AnalystFinding(
            run_id=run.id,
            finding="Bad confidence test",
            recommendation="Fix confidence",
            confidence="super_high",
            sample_size=5,
            evidence_json={},
        )
        db_session.add(invalid_finding)
        db_session.commit()
    db_session.rollback()

    # 4. Draft SET NULL on delete
    db_session.delete(draft)
    db_session.commit()
    db_session.refresh(finding)
    assert finding.draft_id is None

    # 5. Run CASCADE delete on run
    db_session.delete(run)
    db_session.commit()
    assert len(get_findings_for_run(db_session, run.id)) == 0


def test_strategy_entries_crud_and_superseding(db_session: Session) -> None:
    creator = get_or_create_creator(db_session)

    # 1. Create first strategy entry
    entry1 = create_or_update_strategy_entry(
        db_session,
        creator_id=creator.id,
        key="target_audience",
        value_json={"level": "beginner", "focus": "web development"},
        reason="Initial profile setup",
        supporting_finding_ids_json=[],
    )
    assert entry1.id is not None
    assert entry1.status == "active"
    assert entry1.key == "target_audience"

    # 2. Check active entries
    active_entries = get_active_strategy_entries(db_session, creator.id)
    assert len(active_entries) == 1
    assert active_entries[0].id == entry1.id

    retrieved = get_active_strategy_entry(db_session, creator.id, "target_audience")
    assert retrieved is not None
    assert retrieved.id == entry1.id

    # 3. Update entry with new strategy (supersedes old active entry)
    entry2 = create_or_update_strategy_entry(
        db_session,
        creator_id=creator.id,
        key="target_audience",
        value_json={"level": "intermediate", "focus": "fullstack architecture"},
        reason="Post-mortem showed intermediate content has 2x engagement",
        supporting_finding_ids_json=["finding-123"],
    )
    assert entry2.id != entry1.id
    assert entry2.status == "active"

    # Refresh entry1 to verify it is superseded
    db_session.refresh(entry1)
    assert entry1.status == "superseded"

    # Active entries should only return entry2
    active_now = get_active_strategy_entries(db_session, creator.id)
    assert len(active_now) == 1
    assert active_now[0].id == entry2.id
    assert active_now[0].value_json["level"] == "intermediate"

    # History returns both entries
    history = get_strategy_history(db_session, creator.id, "target_audience")
    assert len(history) == 2
    statuses = [h.status for h in history]
    assert "active" in statuses
    assert "superseded" in statuses

    # 4. Check constraint on status (only 'active', 'superseded')
    with pytest.raises(IntegrityError):
        bad_entry = StrategyEntry(
            creator_id=creator.id,
            key="current_experiment",
            value_json={"test": True},
            reason="testing",
            status="archived",
        )
        db_session.add(bad_entry)
        db_session.commit()
    db_session.rollback()

    # 5. Creator CASCADE delete
    assert len(creator.strategy_entries) == 2
    db_session.delete(creator)
    db_session.commit()
    assert len(get_strategy_history(db_session, creator.id)) == 0
