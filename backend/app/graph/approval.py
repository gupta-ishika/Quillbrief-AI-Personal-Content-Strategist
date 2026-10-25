import json
import logging
from typing import Any

from langgraph.types import Command, interrupt
from sqlalchemy.orm import Session

from app.db.base import generate_uuid, utc_now
from app.db.models import Approval, ContentPlan, Run
from app.db.repositories.plans import create_plan_version
from app.db.session import SessionLocal
from app.graph.state import ContentState
from app.schemas.approvals import ApprovalDecisionRequest

logger = logging.getLogger(__name__)


class StaleApprovalError(Exception):
    """Raised when an approval decision is submitted for a decided, cancelled, or mismatched item (UT-20)."""


def approval_node(
    state: ContentState,
    db_session: Session | None = None,
) -> dict[str, Any]:
    """LangGraph Human-In-The-Loop approval node (HITL-01, HITL-02, ADR-006).

    Uses LangGraph interrupt() to pause execution, save checkpoints to SQLite,
    and cleanly resume when the creator submits a decision (approve, reject, edit).
    """
    item_type = state.get("approval_item_type") or "plan"
    item_id = (
        state.get("approval_item_id")
        or state.get("current_plan_id")
        or state.get("current_draft_id")
        or ""
    )
    run_id = state.get("run_id")

    session = db_session or SessionLocal()
    approval_id: str = ""
    try:
        # 1. Fetch or create PENDING approval record in database
        approval = (
            session.query(Approval)
            .filter_by(item_id=item_id, status="PENDING")
            .order_by(Approval.requested_at.desc())
            .first()
        )
        if not approval:
            approval = Approval(
                id=generate_uuid(),
                run_id=run_id,
                item_type=item_type,
                item_id=item_id,
                status="PENDING",
                requested_at=utc_now(),
            )
            session.add(approval)
            session.commit()
            session.refresh(approval)
        approval_id = approval.id

        # 2. Update Run status to WAITING_APPROVAL
        if run_id:
            run_rec = session.query(Run).filter_by(id=run_id).first()
            if run_rec and run_rec.status == "RUNNING":
                run_rec.status = "WAITING_APPROVAL"
                session.commit()
    finally:
        if db_session is None:
            session.close()

    # 3. Trigger LangGraph interrupt to pause execution
    review_payload = {
        "approval_id": approval_id,
        "run_id": run_id,
        "item_type": item_type,
        "item_id": item_id,
        "details": state.get("content_plan")
        if item_type == "plan"
        else state.get("current_draft_id"),
    }

    # interrupt() halts the graph, persists checkpoint to checkpoints.db,
    # and resumes here when Command(resume=decision_dict) is passed.
    user_decision: dict[str, Any] = interrupt(review_payload)

    # 4. Resume processing: apply creator's decision
    decision_val = str(user_decision.get("decision") or "APPROVED").upper()
    feedback_text = user_decision.get("feedback_text")
    edited_content = user_decision.get("edited_content")

    resulting_plan_id = item_id
    resulting_version = state.get("current_plan_version", 1)
    resulting_plan_items = state.get("content_plan", [])

    session = db_session or SessionLocal()
    try:
        app_record = session.query(Approval).filter_by(id=approval_id).first()
        if app_record:
            app_record.status = "DECIDED"
            app_record.decision = decision_val
            app_record.decided_at = utc_now()
            app_record.feedback_text = feedback_text
            if edited_content:
                app_record.edited_content = (
                    json.dumps(edited_content)
                    if isinstance(edited_content, (dict, list))
                    else str(edited_content)
                )

        # Handle Plan decisions (UT-22, ADR-029)
        if item_type == "plan":
            plan = session.query(ContentPlan).filter_by(id=item_id).first()
            if plan:
                if decision_val == "APPROVED":
                    plan.status = "APPROVED"
                    plan.approved_at = utc_now()
                elif decision_val == "REJECTED":
                    plan.status = "REJECTED"
                    plan.feedback_text = feedback_text
                elif decision_val == "EDITED" and edited_content:
                    # EDITED creates a creator-authored APPROVED version in one transaction
                    plan.status = "SUPERSEDED"
                    new_version = plan.version + 1
                    raw_items = (
                        edited_content
                        if isinstance(edited_content, list)
                        else [
                            {
                                "topic": it.topic,
                                "format": it.format,
                                "platform": it.platform,
                                "objective": it.objective,
                                "reason": it.reason,
                                "source_type": it.source_type,
                                "source_ref": it.source_ref,
                                "priority": it.priority,
                                "item_key": it.item_key,
                            }
                            for it in plan.items
                        ]
                    )
                    new_plan = create_plan_version(
                        db=session,
                        lineage_id=plan.lineage_id,
                        version=new_version,
                        run_id=str(run_id or "run_default"),
                        items=raw_items,
                        created_by="creator",
                        previous_version_id=plan.id,
                        status="APPROVED",
                        feedback_text=feedback_text,
                    )
                    new_plan.approved_at = utc_now()
                    resulting_plan_id = new_plan.id
                    resulting_version = new_version
                    resulting_plan_items = raw_items
                    if app_record:
                        app_record.resulting_item_id = new_plan.id

        # Update run status back to RUNNING
        if run_id:
            run_rec = session.query(Run).filter_by(id=run_id).first()
            if run_rec and run_rec.status == "WAITING_APPROVAL":
                run_rec.status = "RUNNING"

        session.commit()
    finally:
        if db_session is None:
            session.close()

    total_steps = state.get("execution_steps", 0) + 1
    route_history = state.get("route_history", []) + ["approval"]

    return {
        "approval_status": decision_val,
        "user_feedback": feedback_text,
        "approval_item_id": resulting_plan_id,
        "current_plan_id": resulting_plan_id,
        "current_plan_version": resulting_version,
        "content_plan": resulting_plan_items,
        "execution_steps": total_steps,
        "route_history": route_history,
        "next_action": "supervisor",
    }


def resume_paused_run(
    graph: Any,
    run_id: str,
    decision_request: ApprovalDecisionRequest,
    db: Session,
) -> dict[str, Any]:
    """Resumes a paused run after human review or backend restart (HITL-02, UT-20).

    Validates exact item ID and pending approval state before resuming.
    """
    approval = (
        db.query(Approval)
        .filter_by(run_id=run_id, status="PENDING")
        .order_by(Approval.requested_at.desc())
        .first()
    )

    if not approval:
        raise StaleApprovalError(f"No pending approval found for run '{run_id}'.")

    if approval.item_id != decision_request.item_id:
        raise StaleApprovalError(
            f"Stale approval: item_id '{decision_request.item_id}' does not match pending item '{approval.item_id}'."
        )

    resume_payload = {
        "decision": decision_request.decision,
        "feedback_text": decision_request.feedback_text,
        "edited_content": decision_request.edited_content,
    }

    config = {"configurable": {"thread_id": run_id}}
    result: dict[str, Any] = graph.invoke(Command(resume=resume_payload), config=config)
    return result
