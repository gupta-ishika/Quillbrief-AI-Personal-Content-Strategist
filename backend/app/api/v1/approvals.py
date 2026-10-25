import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.errors import AppException
from app.db.base import utc_now
from app.db.models import Approval, ContentPlan, Draft, Run
from app.db.repositories import create_plan_version
from app.db.session import get_db
from app.schemas.approvals import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalResponse,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _to_approval_response(db: Session, approval: Approval) -> ApprovalResponse:
    item_details: dict[str, Any] | None = None
    brief_id: str | None = None

    if approval.item_type == "plan":
        plan = db.query(ContentPlan).filter_by(id=approval.item_id).first()
        if plan:
            items = [
                {
                    "id": it.id,
                    "item_key": it.item_key,
                    "topic": it.topic,
                    "format": it.format,
                    "platform": it.platform,
                    "objective": it.objective,
                    "reason": it.reason,
                    "source_type": it.source_type,
                    "source_ref": it.source_ref,
                    "priority": it.priority,
                    "status": it.status,
                }
                for it in plan.items
            ]
            item_details = {
                "id": plan.id,
                "lineage_id": plan.lineage_id,
                "version": plan.version,
                "status": plan.status,
                "created_by": plan.created_by,
                "feedback_text": plan.feedback_text,
                "items": items,
            }
    elif approval.item_type == "draft":
        draft = db.query(Draft).filter_by(id=approval.item_id).first()
        if draft:
            item_details = {
                "id": draft.id,
                "lineage_id": draft.lineage_id,
                "version": draft.version,
                "kind": draft.kind,
                "platform": draft.platform,
                "content": draft.content,
                "status": draft.status,
                "created_by": draft.created_by,
            }
    elif approval.item_type == "depth_increase":
        item_details = {
            "proposal": "depth_increase",
            "reason": approval.feedback_text or "Depth increase suggested by model",
        }

    parsed_edited: Any = None
    if approval.edited_content:
        try:
            parsed_edited = json.loads(approval.edited_content)
        except Exception:
            parsed_edited = approval.edited_content

    return ApprovalResponse(
        id=approval.id,
        run_id=approval.run_id,
        item_type=approval.item_type,  # type: ignore[arg-type]
        item_id=approval.item_id,
        status=approval.status,  # type: ignore[arg-type]
        decision=approval.decision,  # type: ignore[arg-type]
        feedback_text=approval.feedback_text,
        edited_content=parsed_edited,
        resulting_item_id=approval.resulting_item_id,
        brief_id=brief_id,
        item_details=item_details,
        requested_at=approval.requested_at,
        decided_at=approval.decided_at,
    )


@router.get("", response_model=list[ApprovalResponse])
def list_approvals(
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    item_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> list[ApprovalResponse]:
    query = db.query(Approval)
    if status_filter:
        query = query.filter(Approval.status == status_filter)
    if item_type:
        query = query.filter(Approval.item_type == item_type)

    query = query.order_by(Approval.requested_at.desc())
    approvals = query.limit(limit).all()

    return [_to_approval_response(db, a) for a in approvals]


@router.get("/{approval_id}", response_model=ApprovalResponse)
def get_approval_by_id(
    approval_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ApprovalResponse:
    approval = db.query(Approval).filter_by(id=approval_id).first()
    if not approval:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="APPROVAL_NOT_FOUND",
            message=f"Approval '{approval_id}' not found.",
        )
    return _to_approval_response(db, approval)


@router.post("/{approval_id}/decision", response_model=ApprovalDecisionResponse)
def decide_approval_endpoint(
    approval_id: str,
    req: ApprovalDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ApprovalDecisionResponse:
    approval = db.query(Approval).filter_by(id=approval_id).first()
    if not approval:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="APPROVAL_NOT_FOUND",
            message=f"Approval '{approval_id}' not found.",
        )

    # 1. Stale approval checks
    if approval.status != "PENDING":
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="STALE_APPROVAL",
            message="Approval request has already been decided or cancelled.",
        )

    if approval.item_id != req.item_id:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="STALE_APPROVAL",
            message=f"Provided item_id '{req.item_id}' does not match approval item_id '{approval.item_id}'.",
        )

    plan: ContentPlan | None = None
    if approval.item_type == "plan":
        plan = db.query(ContentPlan).filter_by(id=approval.item_id).first()
        if not plan or plan.status == "SUPERSEDED":
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                code="STALE_APPROVAL",
                message="Content plan version has already been superseded.",
            )

    # 2. Validation of decision payloads
    if req.decision == "REJECTED" and not req.feedback_text:
        raise AppException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="FEEDBACK_REQUIRED",
            message="feedback_text is required when decision is REJECTED.",
        )

    if req.decision == "EDITED" and not req.edited_content:
        raise AppException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="EDITED_CONTENT_REQUIRED",
            message="edited_content is required when decision is EDITED.",
        )

    resulting_item_id: str | None = None

    # 3. Apply decision
    if approval.item_type == "plan" and plan:
        if req.decision == "APPROVED":
            plan.status = "APPROVED"
            plan.approved_at = utc_now()
            resulting_item_id = plan.id
        elif req.decision == "REJECTED":
            plan.status = "REJECTED"
            plan.feedback_text = req.feedback_text
        elif req.decision == "EDITED":
            # Deterministic validation of plan items
            raw_items = req.edited_content
            if not isinstance(raw_items, list) or len(raw_items) == 0:
                raise AppException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    code="CHECKS_FAILED",
                    message="edited_content must be a non-empty list of plan items.",
                )
            for idx, item in enumerate(raw_items):
                if not isinstance(item, dict):
                    raise AppException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        code="CHECKS_FAILED",
                        message=f"Item at index {idx} must be an object.",
                    )
                for field in ("topic", "format", "platform", "objective", "reason"):
                    if not item.get(field):
                        raise AppException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            code="CHECKS_FAILED",
                            message=f"Item at index {idx} is missing required field '{field}'.",
                        )

            # Supersede current plan and create creator-authored approved version
            plan.status = "SUPERSEDED"
            new_version = plan.version + 1
            new_plan = create_plan_version(
                db=db,
                lineage_id=plan.lineage_id,
                version=new_version,
                run_id=approval.run_id or plan.run_id,
                items=raw_items,
                created_by="creator",
                previous_version_id=plan.id,
                status="APPROVED",
                feedback_text=req.feedback_text,
            )
            new_plan.approved_at = utc_now()
            resulting_item_id = new_plan.id

    # 4. Update Approval record
    approval.status = "DECIDED"
    approval.decision = req.decision
    approval.feedback_text = req.feedback_text
    if req.edited_content is not None:
        approval.edited_content = (
            json.dumps(req.edited_content)
            if isinstance(req.edited_content, (dict, list))
            else str(req.edited_content)
        )
    approval.resulting_item_id = resulting_item_id
    approval.decided_at = utc_now()

    # 5. If linked to a run, update run status back to RUNNING
    resumed_run_id: str | None = None
    if approval.run_id:
        run = db.query(Run).filter_by(id=approval.run_id).first()
        if run and run.status == "WAITING_APPROVAL":
            run.status = "RUNNING"
            run.updated_at = utc_now()
        resumed_run_id = approval.run_id

    db.commit()
    db.refresh(approval)

    return ApprovalDecisionResponse(
        approval=_to_approval_response(db, approval),
        resulting_item_id=resulting_item_id,
        resumed_run_id=resumed_run_id,
    )
