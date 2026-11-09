from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import AnalystFinding, PerformanceMetric, StrategyEntry


def create_performance_metric(
    db: Session,
    draft_id: str,
    platform: str,
    metric_name: str,
    value: float,
    source: str = "public",
    collected_at: datetime | None = None,
) -> PerformanceMetric:
    metric = PerformanceMetric(
        draft_id=draft_id,
        platform=platform,
        metric_name=metric_name,
        value=value,
        source=source,
        collected_at=collected_at or utc_now(),
    )
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric


def get_metrics_for_draft(db: Session, draft_id: str) -> list[PerformanceMetric]:
    return (
        db.query(PerformanceMetric)
        .filter_by(draft_id=draft_id)
        .order_by(PerformanceMetric.collected_at.asc())
        .all()
    )


def get_metrics_by_platform(db: Session, platform: str) -> list[PerformanceMetric]:
    return (
        db.query(PerformanceMetric)
        .filter_by(platform=platform)
        .order_by(PerformanceMetric.collected_at.desc())
        .all()
    )


def create_analyst_finding(
    db: Session,
    run_id: str,
    finding: str,
    recommendation: str,
    confidence: str,
    sample_size: int,
    evidence_json: Any = None,
    draft_id: str | None = None,
) -> AnalystFinding:
    analyst_finding = AnalystFinding(
        run_id=run_id,
        draft_id=draft_id,
        finding=finding,
        recommendation=recommendation,
        confidence=confidence,
        sample_size=sample_size,
        evidence_json=evidence_json if evidence_json is not None else {},
    )
    db.add(analyst_finding)
    db.commit()
    db.refresh(analyst_finding)
    return analyst_finding


def get_findings_for_run(db: Session, run_id: str) -> list[AnalystFinding]:
    return (
        db.query(AnalystFinding)
        .filter_by(run_id=run_id)
        .order_by(AnalystFinding.created_at.asc())
        .all()
    )


def get_findings_for_draft(db: Session, draft_id: str) -> list[AnalystFinding]:
    return (
        db.query(AnalystFinding)
        .filter_by(draft_id=draft_id)
        .order_by(AnalystFinding.created_at.asc())
        .all()
    )


def get_all_findings(db: Session, limit: int = 100) -> list[AnalystFinding]:
    return (
        db.query(AnalystFinding)
        .order_by(AnalystFinding.created_at.desc())
        .limit(limit)
        .all()
    )


def create_or_update_strategy_entry(
    db: Session,
    creator_id: str,
    key: str,
    value_json: Any,
    reason: str,
    supporting_finding_ids_json: list[str] | None = None,
) -> StrategyEntry:
    # Supersede previous active entries for this (creator_id, key)
    existing_active = (
        db.query(StrategyEntry)
        .filter_by(creator_id=creator_id, key=key, status="active")
        .all()
    )
    for entry in existing_active:
        entry.status = "superseded"

    new_entry = StrategyEntry(
        creator_id=creator_id,
        key=key,
        value_json=value_json,
        reason=reason,
        supporting_finding_ids_json=supporting_finding_ids_json if supporting_finding_ids_json is not None else [],
        status="active",
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    return new_entry


def get_active_strategy_entries(db: Session, creator_id: str) -> list[StrategyEntry]:
    return (
        db.query(StrategyEntry)
        .filter_by(creator_id=creator_id, status="active")
        .order_by(StrategyEntry.key.asc())
        .all()
    )


def get_active_strategy_entry(db: Session, creator_id: str, key: str) -> StrategyEntry | None:
    return (
        db.query(StrategyEntry)
        .filter_by(creator_id=creator_id, key=key, status="active")
        .first()
    )


def get_strategy_history(
    db: Session, creator_id: str, key: str | None = None
) -> list[StrategyEntry]:
    query = db.query(StrategyEntry).filter_by(creator_id=creator_id)
    if key:
        query = query.filter_by(key=key)
    return query.order_by(StrategyEntry.created_at.desc()).all()
