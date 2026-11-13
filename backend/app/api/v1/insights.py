"""Insights, Analyst Findings, and Strategy API router (API.md Section 6 and Phase 4 API-04).

Implements:
- GET /insights/comments: Current comment insights passing channel rule with 90-day retention handling
- GET /findings: Analyst findings with recommendation, confidence, sample size, and linked draft
- GET /strategy: Active strategy entries with reasons and supporting findings; ?include=history for superseded
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.errors import AppException
from app.db.models import AnalystFinding, CommentInsight, StrategyEntry
from app.db.repositories import (
    get_active_strategy_entries,
    get_active_strategy_entry,
    get_all_findings,
    get_current_insights_for_channel,
    get_findings_for_draft,
    get_findings_for_run,
    get_or_create_creator,
    get_strategy_history,
)
from app.db.session import get_db
from app.schemas.insights import (
    AnalystFindingResponse,
    CommentInsightResponse,
    StrategyEntryResponse,
)
from app.schemas.insights import (
    CommentInsightExample as CommentInsightExampleSchema,
)

router = APIRouter(tags=["insights", "findings", "strategy"])


def _to_comment_insight_response(insight: CommentInsight) -> CommentInsightResponse:
    examples: list[CommentInsightExampleSchema] = []
    for ex in insight.examples:
        comment = ex.comment
        if comment and comment.text:
            examples.append(
                CommentInsightExampleSchema(
                    comment_id=ex.comment_id,
                    text=comment.text,
                    like_count=comment.like_count,
                    published_at=comment.published_at,
                    available=True,
                )
            )
        elif comment:
            # Comment text cleared after 90 days (ADR-033)
            examples.append(
                CommentInsightExampleSchema(
                    comment_id=ex.comment_id,
                    text=None,
                    like_count=comment.like_count,
                    published_at=comment.published_at,
                    available=False,
                )
            )
        else:
            examples.append(
                CommentInsightExampleSchema(
                    comment_id=ex.comment_id,
                    text=None,
                    like_count=0,
                    published_at=insight.created_at,
                    available=False,
                )
            )

    return CommentInsightResponse(
        id=insight.id,
        creator_id=insight.creator_id,
        run_id=insight.run_id,
        theme_label=insight.theme_label,
        comment_count=insight.comment_count,
        examples=examples,
        coverage_analyzed=insight.coverage_analyzed,
        coverage_total=insight.coverage_total,
        status=insight.status,  # type: ignore[arg-type]
        created_at=insight.created_at,
    )


def _to_finding_response(finding: AnalystFinding) -> AnalystFindingResponse:
    evidence = finding.evidence_json if isinstance(finding.evidence_json, dict) else {}
    return AnalystFindingResponse(
        id=finding.id,
        run_id=finding.run_id,
        draft_id=finding.draft_id,
        finding=finding.finding,
        recommendation=finding.recommendation,
        confidence=finding.confidence,  # type: ignore[arg-type]
        sample_size=finding.sample_size,
        evidence=evidence,
        created_at=finding.created_at,
    )


def _to_strategy_response(entry: StrategyEntry) -> StrategyEntryResponse:
    supporting_findings = entry.supporting_finding_ids_json or []
    if isinstance(supporting_findings, list):
        findings_list = [str(f) for f in supporting_findings]
    else:
        findings_list = []

    return StrategyEntryResponse(
        id=entry.id,
        creator_id=entry.creator_id,
        key=entry.key,
        value=entry.value_json,
        reason=entry.reason,
        supporting_finding_ids=findings_list,
        status=entry.status,  # type: ignore[arg-type]
        created_at=entry.created_at,
    )


@router.get("/insights/comments", response_model=list[CommentInsightResponse])
@router.get("/insights", response_model=list[CommentInsightResponse])
def get_comment_insights(
    db: Annotated[Session, Depends(get_db)],
) -> list[CommentInsightResponse]:
    """Returns current comment insights adhering strictly to the Channel Rule (ADR-032)."""
    creator = get_or_create_creator(db)
    if not creator.youtube_channel_id:
        return []

    insights = get_current_insights_for_channel(db, creator.youtube_channel_id)
    return [_to_comment_insight_response(ins) for ins in insights]


@router.get("/findings", response_model=list[AnalystFindingResponse])
def get_findings(
    db: Annotated[Session, Depends(get_db)],
    draft_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AnalystFindingResponse]:
    """Returns Analyst findings with recommendations, confidence, and linked draft."""
    if draft_id:
        findings = get_findings_for_draft(db, draft_id)
    elif run_id:
        findings = get_findings_for_run(db, run_id)
    else:
        findings = get_all_findings(db, limit=limit)

    return [_to_finding_response(f) for f in findings]


@router.get("/findings/{finding_id}", response_model=AnalystFindingResponse)
def get_finding_by_id(
    finding_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> AnalystFindingResponse:
    """Returns a single Analyst finding by ID."""
    finding = db.query(AnalystFinding).filter_by(id=finding_id).first()
    if not finding:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FINDING_NOT_FOUND",
            message=f"Finding '{finding_id}' not found",
        )
    return _to_finding_response(finding)


@router.get("/strategy", response_model=list[StrategyEntryResponse])
def get_strategy(
    db: Annotated[Session, Depends(get_db)],
    include: str | None = Query(default=None),
) -> list[StrategyEntryResponse]:
    """Returns active strategy entries with reasons and supporting findings.

    Add ?include=history to include superseded entries.
    """
    creator = get_or_create_creator(db)
    if include == "history":
        entries = get_strategy_history(db, creator.id)
    else:
        entries = get_active_strategy_entries(db, creator.id)

    return [_to_strategy_response(e) for e in entries]


@router.get("/strategy/{key}", response_model=StrategyEntryResponse)
def get_strategy_by_key(
    key: str,
    db: Annotated[Session, Depends(get_db)],
) -> StrategyEntryResponse:
    """Returns the active strategy entry for a specific key."""
    creator = get_or_create_creator(db)
    entry = get_active_strategy_entry(db, creator.id, key)
    if not entry:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="STRATEGY_NOT_FOUND",
            message=f"Strategy entry for key '{key}' not found",
        )
    return _to_strategy_response(entry)
