"""Drafts API router (API.md Section 4 and VER-02).

Implements draft versioning: lineage, immutable versions, exact-version approvals,
editing outside approvals with deterministic quality checks, and mark-as-posted tracking.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.errors import AppException
from app.db.base import utc_now
from app.db.models import Approval, CriticEvaluation, Draft
from app.db.repositories.plans import create_approval, create_draft_version
from app.db.session import get_db
from app.schemas.drafts import (
    CriticEvaluationResponse,
    DraftEditRequest,
    DraftEditResponse,
    DraftResponse,
    DraftVersionSummary,
    LinkPostedRequest,
    MarkPostedRequest,
    MarkPostedResponse,
)
from app.tools.draft_checker import check_draft

router = APIRouter(prefix="/drafts", tags=["drafts"])


def _to_draft_response(db: Session, draft: Draft) -> DraftResponse:
    latest_version = (
        db.query(func.max(Draft.version)).filter_by(lineage_id=draft.lineage_id).scalar()
        or draft.version
    )
    is_latest = draft.version == latest_version

    # Fetch CriticEvaluation for this draft
    evaluation = db.query(CriticEvaluation).filter_by(draft_id=draft.id).first()
    critic_resp = None
    if evaluation:
        critic_resp = CriticEvaluationResponse(
            id=evaluation.id,
            draft_id=evaluation.draft_id,
            review_number=evaluation.review_number,
            score=evaluation.score,
            passed=evaluation.passed,
            rubric=evaluation.rubric_json or {},
            deterministic=evaluation.deterministic_json or {},
            feedback=evaluation.feedback_json or {},
            created_at=evaluation.created_at,
        )

    # Fetch repurposed child drafts
    children = db.query(Draft.id).filter_by(parent_draft_id=draft.id).all()
    child_ids = [c[0] for c in children]

    return DraftResponse(
        id=draft.id,
        lineage_id=draft.lineage_id,
        version=draft.version,
        previous_version_id=draft.previous_version_id,
        plan_item_id=draft.plan_item_id,
        item_key=draft.item_key,
        parent_draft_id=draft.parent_draft_id,
        kind=draft.kind,  # type: ignore[arg-type]
        platform=draft.platform,
        content=draft.content,
        created_by=draft.created_by,  # type: ignore[arg-type]
        status=draft.status,  # type: ignore[arg-type]
        is_latest=is_latest,
        critic_evaluation=critic_resp,
        posted_at=draft.posted_at,
        posted_ref=draft.posted_ref,  # type: ignore[arg-type]
        posted_url=draft.posted_url,
        posted_platform_id=draft.posted_platform_id,
        child_draft_ids=child_ids,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


@router.get("", response_model=list[DraftResponse])
def list_drafts(
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    platform: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    plan_item_id: Annotated[str | None, Query()] = None,
    lineage_id: Annotated[str | None, Query()] = None,
    is_latest: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> list[DraftResponse]:
    query = db.query(Draft)

    if status_filter:
        query = query.filter(Draft.status == status_filter)
    if platform:
        query = query.filter(Draft.platform == platform)
    if kind:
        query = query.filter(Draft.kind == kind)
    if plan_item_id:
        query = query.filter(Draft.plan_item_id == plan_item_id)
    if lineage_id:
        query = query.filter(Draft.lineage_id == lineage_id)

    if is_latest is True:
        # Subquery to select max version per lineage
        subquery = (
            db.query(Draft.lineage_id, func.max(Draft.version).label("max_ver"))
            .group_by(Draft.lineage_id)
            .subquery()
        )
        query = query.join(
            subquery,
            (Draft.lineage_id == subquery.c.lineage_id) & (Draft.version == subquery.c.max_ver),
        )

    drafts = query.order_by(Draft.created_at.desc()).limit(limit).all()
    return [_to_draft_response(db, d) for d in drafts]


@router.get("/{draft_id}", response_model=DraftResponse)
def get_draft_by_id(
    draft_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> DraftResponse:
    draft = db.query(Draft).filter_by(id=draft_id).first()
    if not draft:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="DRAFT_NOT_FOUND",
            message=f"Draft '{draft_id}' not found.",
        )
    return _to_draft_response(db, draft)


@router.get("/{draft_id}/versions", response_model=list[DraftVersionSummary])
def get_draft_versions(
    draft_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[DraftVersionSummary]:
    draft = db.query(Draft).filter_by(id=draft_id).first()
    if not draft:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="DRAFT_NOT_FOUND",
            message=f"Draft '{draft_id}' not found.",
        )

    lineage_drafts = (
        db.query(Draft).filter_by(lineage_id=draft.lineage_id).order_by(Draft.version.desc()).all()
    )

    return [
        DraftVersionSummary(
            version=d.version,
            status=d.status,  # type: ignore[arg-type]
            created_by=d.created_by,
            created_at=d.created_at,
            is_approved=d.status == "APPROVED",
            is_posted=d.status == "POSTED",
        )
        for d in lineage_drafts
    ]


@router.post(
    "/{draft_id}/edit",
    status_code=status.HTTP_201_CREATED,
    response_model=DraftEditResponse,
)
def edit_draft_outside_approval(
    draft_id: str,
    req: DraftEditRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DraftEditResponse:
    draft = db.query(Draft).filter_by(id=draft_id).first()
    if not draft:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="DRAFT_NOT_FOUND",
            message=f"Draft '{draft_id}' not found.",
        )

    # 1. Optimistic locking / version check
    latest_draft = (
        db.query(Draft)
        .filter_by(lineage_id=draft.lineage_id)
        .order_by(Draft.version.desc())
        .first()
    )

    if (
        not latest_draft
        or latest_draft.version != req.expected_version
        or draft.id != latest_draft.id
    ):
        current_version = latest_draft.version if latest_draft else draft.version
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="STALE_VERSION",
            message=f"Version mismatch: expected {req.expected_version}, but latest version is {current_version}.",
        )

    # 2. Run deterministic checks (ADR-023, FR-15)
    check_result = check_draft(req.content, draft.kind, draft.platform)
    if not check_result.passed:
        raise AppException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="CHECKS_FAILED",
            message="Draft failed deterministic quality checks.",
            details={
                "issues": check_result.issues,
                "missing_sections": check_result.missing_sections,
                "metrics": check_result.metrics,
            },
        )

    # 3. Cancel any pending approvals on earlier draft
    db.query(Approval).filter_by(item_id=draft.id, status="PENDING").update({"status": "CANCELLED"})

    # 4. Mark earlier version SUPERSEDED
    draft.status = "SUPERSEDED"

    # 5. Create new version in PENDING_APPROVAL authored by creator
    new_version = draft.version + 1
    new_draft = create_draft_version(
        db=db,
        lineage_id=draft.lineage_id,
        version=new_version,
        kind=draft.kind,
        platform=draft.platform,
        content=req.content,
        created_by="creator",
        previous_version_id=draft.id,
        plan_item_id=draft.plan_item_id,
        item_key=draft.item_key,
        parent_draft_id=draft.parent_draft_id,
        status="PENDING_APPROVAL",
    )

    # 6. Create new approval request for this exact version
    new_approval = create_approval(
        db=db,
        item_type="draft",
        item_id=new_draft.id,
        run_id=None,
    )

    db.commit()
    db.refresh(new_draft)
    db.refresh(new_approval)

    return DraftEditResponse(draft_id=new_draft.id, approval_id=new_approval.id)


@router.post("/{draft_id}/mark-posted", response_model=MarkPostedResponse)
def mark_draft_as_posted(
    draft_id: str,
    req: MarkPostedRequest,
    db: Annotated[Session, Depends(get_db)],
) -> MarkPostedResponse:
    draft = db.query(Draft).filter_by(id=draft_id).first()
    if not draft:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="DRAFT_NOT_FOUND",
            message=f"Draft '{draft_id}' not found.",
        )

    # 1. Must be latest version
    latest = (
        db.query(Draft)
        .filter_by(lineage_id=draft.lineage_id)
        .order_by(Draft.version.desc())
        .first()
    )
    if not latest or draft.id != latest.id:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="STALE_VERSION",
            message="Only the latest version of an approved draft can be marked as posted.",
        )

    # 2. Must be APPROVED (UT-11)
    if draft.status != "APPROVED":
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="NOT_APPROVED",
            message=f"Draft status is '{draft.status}'. Only APPROVED drafts can be marked as posted.",
        )

    # 3. Determine posted reference
    posted_ref: str
    if req.posted_url:
        posted_ref = "url"
    elif req.platform_content_id:
        posted_ref = "platform_id"
    else:
        posted_ref = "none"

    draft.status = "POSTED"
    draft.posted_at = req.posted_at or utc_now()
    draft.posted_ref = posted_ref
    draft.posted_url = req.posted_url
    draft.posted_platform_id = req.platform_content_id
    draft.updated_at = utc_now()

    db.commit()
    db.refresh(draft)

    analytics_eligible = posted_ref in ("url", "platform_id")

    return MarkPostedResponse(
        draft_id=draft.id,
        status="POSTED",
        posted_ref=posted_ref,  # type: ignore[arg-type]
        analytics_eligible=analytics_eligible,
    )


@router.post("/{draft_id}/link-posted", response_model=DraftResponse)
def link_posted_draft(
    draft_id: str,
    req: LinkPostedRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DraftResponse:
    draft = db.query(Draft).filter_by(id=draft_id).first()
    if not draft:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="DRAFT_NOT_FOUND",
            message=f"Draft '{draft_id}' not found.",
        )

    if draft.status != "POSTED":
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="NOT_POSTED",
            message="Only posted drafts can have platform links attached.",
        )

    if not req.posted_url and not req.platform_content_id:
        raise AppException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="LINK_REQUIRED",
            message="Either posted_url or platform_content_id must be provided.",
        )

    if req.posted_url:
        draft.posted_url = req.posted_url
        draft.posted_ref = "url"
    elif req.platform_content_id:
        draft.posted_platform_id = req.platform_content_id
        draft.posted_ref = "platform_id"

    draft.updated_at = utc_now()
    db.commit()
    db.refresh(draft)

    return _to_draft_response(db, draft)
