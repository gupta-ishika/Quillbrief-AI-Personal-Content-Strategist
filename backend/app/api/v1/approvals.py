import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.errors import AppException
from app.db.base import utc_now
from app.db.models import Approval, ContentPlan, CriticEvaluation, Draft, Run, Task
from app.db.repositories import create_plan_version
from app.db.repositories.plans import create_draft_version
from app.db.repositories.runs import record_run_event
from app.db.session import get_db
from app.schemas.approvals import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalResponse,
)
from app.tools.draft_checker import check_draft

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
            eval_rec = db.query(CriticEvaluation).filter_by(draft_id=draft.id).first()
            critic_eval = None
            if eval_rec:
                critic_eval = {
                    "id": eval_rec.id,
                    "draft_id": eval_rec.draft_id,
                    "review_number": eval_rec.review_number,
                    "score": eval_rec.score,
                    "passed": eval_rec.passed,
                    "rubric": eval_rec.rubric_json or {},
                    "deterministic": eval_rec.deterministic_json or {},
                    "feedback": eval_rec.feedback_json or {},
                    "created_at": eval_rec.created_at.isoformat() if eval_rec.created_at else None,
                }
            item_details = {
                "id": draft.id,
                "lineage_id": draft.lineage_id,
                "version": draft.version,
                "kind": draft.kind,
                "platform": draft.platform,
                "content": draft.content,
                "status": draft.status,
                "created_by": draft.created_by,
                "critic_evaluation": critic_eval,
                "posted_at": draft.posted_at.isoformat() if draft.posted_at else None,
                "posted_ref": draft.posted_ref,
                "posted_url": draft.posted_url,
                "posted_platform_id": draft.posted_platform_id,
            }
    elif approval.item_type == "depth_increase":
        current_depth = "standard"
        unfinished: list[str] = []
        if approval.run_id:
            run_obj = db.query(Run).filter_by(id=approval.run_id).first()
            if run_obj:
                current_depth = run_obj.depth_level
            tasks = (
                db.query(Task)
                .filter_by(run_id=approval.run_id)
                .order_by(Task.position.asc())
                .all()
            )
            unfinished = [t.title for t in tasks if t.status not in ("DONE", "SKIPPED")]
        proposed_depth = "deep" if current_depth == "standard" else "standard"
        item_details = {
            "proposal": "depth_increase",
            "current_depth": current_depth,
            "proposed_depth": proposed_depth,
            "reason": approval.feedback_text
            or f"Depth increase proposal from {current_depth} to {proposed_depth}",
            "unfinished_tasks": unfinished,
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
    draft: Draft | None = None
    if approval.item_type == "plan":
        plan = db.query(ContentPlan).filter_by(id=approval.item_id).first()
        if not plan or plan.status == "SUPERSEDED":
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                code="STALE_APPROVAL",
                message="Content plan version has already been superseded.",
            )
    elif approval.item_type == "draft":
        draft = db.query(Draft).filter_by(id=approval.item_id).first()
        if not draft or draft.status == "SUPERSEDED":
            raise AppException(
                status_code=status.HTTP_409_CONFLICT,
                code="STALE_APPROVAL",
                message="Draft version has already been superseded.",
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
    elif approval.item_type == "draft" and draft:
        if req.decision == "APPROVED":
            draft.status = "APPROVED"
            draft.updated_at = utc_now()
            resulting_item_id = draft.id
        elif req.decision == "REJECTED":
            draft.status = "REJECTED"
            draft.updated_at = utc_now()
            resulting_item_id = draft.id
        elif req.decision == "EDITED":
            content_str = (
                req.edited_content
                if isinstance(req.edited_content, str)
                else json.dumps(req.edited_content)
            )
            check_result = check_draft(content_str, draft.kind, draft.platform)
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
            draft.status = "SUPERSEDED"
            draft.updated_at = utc_now()
            new_version = draft.version + 1
            new_draft = create_draft_version(
                db=db,
                lineage_id=draft.lineage_id,
                version=new_version,
                kind=draft.kind,
                platform=draft.platform,
                content=content_str,
                created_by="creator",
                previous_version_id=draft.id,
                plan_item_id=draft.plan_item_id,
                item_key=draft.item_key,
                parent_draft_id=draft.parent_draft_id,
                status="APPROVED",
            )
            resulting_item_id = new_draft.id

    elif approval.item_type == "depth_increase":
        resulting_item_id = approval.item_id
        if req.decision == "APPROVED" and approval.run_id:
            run = db.query(Run).filter_by(id=approval.run_id).first()
            if run:
                old_depth = run.depth_level
                new_depth = "deep" if old_depth == "standard" else "standard"
                run.depth_level = new_depth
                run.stop_reason = None
                record_run_event(
                    db,
                    run.id,
                    "note",
                    {
                        "message": f"Depth level raised from '{old_depth}' to '{new_depth}' for run '{run.id}'."
                    },
                )

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

    # 5. If linked to a run, update run status back to RUNNING if approved
    resumed_run_id: str | None = None
    if approval.run_id:
        run = db.query(Run).filter_by(id=approval.run_id).first()
        if run:
            if req.decision == "APPROVED":
                if run.status in ("WAITING_APPROVAL", "STOPPED"):
                    run.status = "RUNNING"
                    run.updated_at = utc_now()
                resumed_run_id = approval.run_id
            elif req.decision == "REJECTED":
                if run.status == "WAITING_APPROVAL":
                    run.status = "RUNNING"
                    resumed_run_id = approval.run_id

    db.commit()
    db.refresh(approval)

    return ApprovalDecisionResponse(
        approval=_to_approval_response(db, approval),
        resulting_item_id=resulting_item_id,
        resumed_run_id=resumed_run_id,
    )
