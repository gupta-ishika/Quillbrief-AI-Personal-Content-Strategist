"""Plans API router (API.md Section 4 and VER-01).

Implements plan versioning: lineage, immutable versions, exact-version approvals,
and plan editing outside approval decisions.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.errors import AppException
from app.db.base import generate_uuid
from app.db.models import Approval, ContentPlan
from app.db.repositories import create_approval, create_plan_version
from app.db.session import get_db
from app.schemas.plans import (
    PlanEditRequest,
    PlanEditResponse,
    PlanItemResponse,
    PlanResponse,
)

router = APIRouter(prefix="/plans", tags=["plans"])


def _to_plan_response(db: Session, plan: ContentPlan) -> PlanResponse:
    latest_version = (
        db.query(func.max(ContentPlan.version)).filter_by(lineage_id=plan.lineage_id).scalar()
        or plan.version
    )
    is_latest = plan.version == latest_version

    items = [
        PlanItemResponse(
            id=it.id,
            plan_id=it.plan_id,
            item_key=it.item_key,
            topic=it.topic,
            format=it.format,
            platform=it.platform,
            objective=it.objective,
            reason=it.reason,
            source_type=it.source_type,  # type: ignore[arg-type]
            source_ref=it.source_ref,
            priority=it.priority,
            scheduled_day=it.scheduled_day,
            status=it.status,  # type: ignore[arg-type]
        )
        for it in plan.items
    ]

    return PlanResponse(
        id=plan.id,
        lineage_id=plan.lineage_id,
        version=plan.version,
        previous_version_id=plan.previous_version_id,
        run_id=plan.run_id,
        created_by=plan.created_by,  # type: ignore[arg-type]
        status=plan.status,  # type: ignore[arg-type]
        feedback_text=plan.feedback_text,
        is_latest=is_latest,
        brief_id=None,
        items=items,
        created_at=plan.created_at,
        approved_at=plan.approved_at,
    )


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan_by_id(
    plan_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> PlanResponse:
    plan = db.query(ContentPlan).filter_by(id=plan_id).first()
    if not plan:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PLAN_NOT_FOUND",
            message=f"Content plan '{plan_id}' not found.",
        )
    return _to_plan_response(db, plan)


@router.post(
    "/{plan_id}/edit",
    status_code=status.HTTP_201_CREATED,
    response_model=PlanEditResponse,
)
def edit_plan_outside_approval(
    plan_id: str,
    req: PlanEditRequest,
    db: Annotated[Session, Depends(get_db)],
) -> PlanEditResponse:
    plan = db.query(ContentPlan).filter_by(id=plan_id).first()
    if not plan:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PLAN_NOT_FOUND",
            message=f"Content plan '{plan_id}' not found.",
        )

    # 1. Optimistic locking / version check (API.md Section 4)
    latest_plan = (
        db.query(ContentPlan)
        .filter_by(lineage_id=plan.lineage_id)
        .order_by(ContentPlan.version.desc())
        .first()
    )

    if not latest_plan or latest_plan.version != req.expected_version or plan.id != latest_plan.id:
        current_version = latest_plan.version if latest_plan else plan.version
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="STALE_VERSION",
            message=f"Version mismatch: expected {req.expected_version}, but latest version is {current_version}.",
        )

    # 2. Cancel any pending approvals on the superseded plan
    db.query(Approval).filter_by(item_id=plan.id, status="PENDING").update({"status": "CANCELLED"})

    # 3. Mark earlier version SUPERSEDED
    plan.status = "SUPERSEDED"

    # 4. Map edited items, preserving item_key or generating new key
    raw_items = []
    for it in req.items:
        raw_items.append(
            {
                "item_key": it.item_key or generate_uuid(),
                "topic": it.topic,
                "format": it.format,
                "platform": it.platform,
                "objective": it.objective,
                "reason": it.reason,
                "source_type": it.source_type,
                "source_ref": it.source_ref,
                "priority": it.priority,
                "scheduled_day": it.scheduled_day,
                "status": it.status,
            }
        )

    # 5. Create new version in PENDING_APPROVAL authored by creator
    new_version = plan.version + 1
    new_plan = create_plan_version(
        db=db,
        lineage_id=plan.lineage_id,
        version=new_version,
        run_id=plan.run_id,
        items=raw_items,
        created_by="creator",
        previous_version_id=plan.id,
        status="PENDING_APPROVAL",
    )

    # 6. Create new approval request for this exact version
    new_approval = create_approval(
        db=db,
        item_type="plan",
        item_id=new_plan.id,
        run_id=plan.run_id,
    )

    db.commit()
    db.refresh(new_plan)
    db.refresh(new_approval)

    return PlanEditResponse(plan_id=new_plan.id, approval_id=new_approval.id)
