from typing import Any

from sqlalchemy.orm import Session

from app.db.base import generate_uuid, utc_now
from app.db.models import Approval, ContentPlan, CriticEvaluation, Draft, PlanItem


def create_plan_version(
    db: Session,
    lineage_id: str,
    version: int,
    run_id: str,
    items: list[dict[str, Any]],
    created_by: str = "strategist",
    previous_version_id: str | None = None,
    status: str = "DRAFT",
    feedback_text: str | None = None,
) -> ContentPlan:
    plan = ContentPlan(
        lineage_id=lineage_id,
        version=version,
        previous_version_id=previous_version_id,
        run_id=run_id,
        created_by=created_by,
        status=status,
        feedback_text=feedback_text,
    )
    db.add(plan)
    db.flush()

    for item_data in items:
        plan_item = PlanItem(
            plan_id=plan.id,
            item_key=item_data.get("item_key", generate_uuid()),
            topic=item_data["topic"],
            format=item_data["format"],
            platform=item_data["platform"],
            objective=item_data["objective"],
            reason=item_data["reason"],
            source_type=item_data.get("source_type", "own_idea"),
            source_ref=item_data.get("source_ref"),
            priority=item_data.get("priority", 1),
            scheduled_day=item_data.get("scheduled_day"),
            status=item_data.get("status", "PLANNED"),
        )
        db.add(plan_item)

    db.commit()
    db.refresh(plan)
    return plan


def get_latest_plan_version(db: Session, lineage_id: str) -> ContentPlan | None:
    return (
        db.query(ContentPlan)
        .filter_by(lineage_id=lineage_id)
        .order_by(ContentPlan.version.desc())
        .first()
    )


def create_draft_version(
    db: Session,
    lineage_id: str,
    version: int,
    kind: str,
    platform: str,
    content: str,
    created_by: str = "model",
    plan_item_id: str | None = None,
    item_key: str | None = None,
    previous_version_id: str | None = None,
    parent_draft_id: str | None = None,
    status: str = "WRITING",
) -> Draft:
    draft = Draft(
        lineage_id=lineage_id,
        version=version,
        previous_version_id=previous_version_id,
        plan_item_id=plan_item_id,
        item_key=item_key,
        parent_draft_id=parent_draft_id,
        kind=kind,
        platform=platform,
        content=content,
        created_by=created_by,
        status=status,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def get_latest_draft_version(db: Session, lineage_id: str) -> Draft | None:
    return db.query(Draft).filter_by(lineage_id=lineage_id).order_by(Draft.version.desc()).first()


def create_approval(
    db: Session,
    item_type: str,
    item_id: str,
    run_id: str | None = None,
) -> Approval:
    approval = Approval(
        run_id=run_id,
        item_type=item_type,
        item_id=item_id,
        status="PENDING",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def decide_approval(
    db: Session,
    approval_id: str,
    decision: str,
    feedback_text: str | None = None,
    edited_content: str | None = None,
    resulting_item_id: str | None = None,
) -> Approval | None:
    approval = db.query(Approval).filter_by(id=approval_id).first()
    if not approval or approval.status != "PENDING":
        return None

    approval.status = "DECIDED"
    approval.decision = decision
    approval.feedback_text = feedback_text
    approval.edited_content = edited_content
    approval.resulting_item_id = resulting_item_id
    approval.decided_at = utc_now()

    db.commit()
    db.refresh(approval)
    return approval


def create_critic_evaluation(
    db: Session,
    draft_id: str,
    review_number: int,
    score: float,
    passed: bool,
    rubric_json: dict[str, Any],
    deterministic_json: dict[str, Any],
    feedback_json: dict[str, Any],
) -> CriticEvaluation:
    evaluation = CriticEvaluation(
        draft_id=draft_id,
        review_number=review_number,
        score=score,
        passed=passed,
        rubric_json=rubric_json,
        deterministic_json=deterministic_json,
        feedback_json=feedback_json,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return evaluation


def get_critic_evaluation_for_draft(db: Session, draft_id: str) -> CriticEvaluation | None:
    return db.query(CriticEvaluation).filter_by(draft_id=draft_id).first()


def get_draft_by_id(db: Session, draft_id: str) -> Draft | None:
    return db.query(Draft).filter_by(id=draft_id).first()


def update_draft_status(
    db: Session,
    draft_id: str,
    status: str,
) -> Draft | None:
    draft = db.query(Draft).filter_by(id=draft_id).first()
    if not draft:
        return None
    draft.status = status
    draft.updated_at = utc_now()
    db.commit()
    db.refresh(draft)
    return draft
