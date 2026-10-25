from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.errors import AppException
from app.db.base import utc_now
from app.db.models import Approval, RoutingLog, Run
from app.db.repositories import (
    create_goal,
    create_run,
    get_or_create_creator,
    get_run,
    get_run_tasks,
    get_setting,
)
from app.db.session import get_db
from app.schemas.runs import (
    RoutingLogItem,
    RunCreateRequest,
    RunCreateResponse,
    RunResponse,
    TaskResponse,
)

router = APIRouter(prefix="/runs", tags=["runs"])


def _to_run_response(db: Session, run: Run) -> RunResponse:
    tasks = get_run_tasks(db, run.id)
    pending_app = db.query(Approval).filter_by(run_id=run.id, status="PENDING").first()
    return RunResponse(
        id=run.id,
        goal_id=run.goal_id,
        run_type=run.run_type,  # type: ignore[arg-type]
        depth_level=run.depth_level,  # type: ignore[arg-type]
        status=run.status,  # type: ignore[arg-type]
        step_count=run.step_count,
        tokens_used=run.tokens_used,
        stop_reason=run.stop_reason,
        degraded=run.degraded,
        degraded_reason=run.degraded_reason,
        current_node=None,
        tasks=[
            TaskResponse(
                id=t.id,
                run_id=t.run_id,
                title=t.title,
                agent=t.agent,
                position=t.position,
                status=t.status,  # type: ignore[arg-type]
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in tasks
        ],
        pending_approval_id=pending_app.id if pending_app else None,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=RunCreateResponse)
def start_run(
    req: RunCreateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> RunCreateResponse:
    # 1. Onboarding check
    onboarding_completed = get_setting(db, "onboarding_completed")
    if not onboarding_completed:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="ONBOARDING_REQUIRED",
            message="Onboarding must be completed before starting a run.",
        )

    # 2. Deletion check
    if get_setting(db, "deletion_in_progress"):
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="DELETION_IN_PROGRESS",
            message="Creator data deletion is currently in progress.",
        )

    # 3. Active run check
    active_run = (
        db.query(Run)
        .filter(Run.run_type == "goal", Run.status.in_(["RUNNING", "WAITING_APPROVAL"]))
        .first()
    )
    if active_run:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="RUN_ACTIVE",
            message="Another goal run is currently active.",
        )

    # 4. Resolve depth level
    default_depth = get_setting(db, "default_depth_level") or "standard"
    depth = req.depth_level or default_depth

    # 5. Create Goal and Run
    creator = get_or_create_creator(db)
    goal = create_goal(db, creator_id=creator.id, text=req.goal_text)
    run = create_run(db, run_type="goal", depth_level=depth, goal_id=goal.id)

    return RunCreateResponse(run_id=run.id, status=run.status)  # type: ignore[arg-type]


@router.get("", response_model=list[RunResponse])
def list_runs(
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    run_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> list[RunResponse]:
    query = db.query(Run)
    if status_filter:
        query = query.filter(Run.status == status_filter)
    if run_type:
        query = query.filter(Run.run_type == run_type)

    query = query.order_by(Run.created_at.desc())
    runs = query.limit(limit).all()

    return [_to_run_response(db, run) for run in runs]


@router.get("/{run_id}", response_model=RunResponse)
def get_run_by_id(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> RunResponse:
    run = get_run(db, run_id)
    if not run:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RUN_NOT_FOUND",
            message=f"Run '{run_id}' not found.",
        )
    return _to_run_response(db, run)


@router.get("/{run_id}/routing-log", response_model=list[RoutingLogItem])
def get_run_routing_log(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[RoutingLogItem]:
    run = get_run(db, run_id)
    if not run:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RUN_NOT_FOUND",
            message=f"Run '{run_id}' not found.",
        )

    logs = (
        db.query(RoutingLog).filter_by(run_id=run_id).order_by(RoutingLog.step_number.asc()).all()
    )

    items: list[RoutingLogItem] = []
    for log in logs:
        eligible: list[str] = (
            log.eligible_nodes_json if isinstance(log.eligible_nodes_json, list) else []
        )
        items.append(
            RoutingLogItem(
                step_number=log.step_number,
                from_node=log.from_node,
                to_node=log.to_node,
                reason=log.reason,
                decided_by=log.decided_by,  # type: ignore[arg-type]
                eligible_nodes=eligible,
                output_status=log.output_status,  # type: ignore[arg-type]
                invalid_category=log.invalid_category,  # type: ignore[arg-type]
                tokens_in=log.tokens_in,
                tokens_out=log.tokens_out,
                created_at=log.created_at,
            )
        )
    return items


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> RunResponse:
    run = get_run(db, run_id)
    if not run:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RUN_NOT_FOUND",
            message=f"Run '{run_id}' not found.",
        )

    if run.status in ("COMPLETED", "FAILED", "STOPPED"):
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="RUN_ALREADY_FINISHED",
            message=f"Run '{run_id}' is already finished with status '{run.status}'.",
        )

    # Cancel pending approvals belonging to this run
    db.query(Approval).filter_by(run_id=run_id, status="PENDING").update({"status": "CANCELLED"})

    run.status = "STOPPED"
    run.stop_reason = "Cancelled by user"
    run.finished_at = utc_now()
    run.updated_at = utc_now()
    db.commit()
    db.refresh(run)

    return _to_run_response(db, run)


@router.post(
    "/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED, response_model=RunCreateResponse
)
def resume_run(
    run_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> RunCreateResponse:
    run = get_run(db, run_id)
    if not run:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RUN_NOT_FOUND",
            message=f"Run '{run_id}' not found.",
        )

    if run.status != "INTERRUPTED":
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code="RUN_NOT_RESUMABLE",
            message=f"Run with status '{run.status}' cannot be resumed (must be INTERRUPTED).",
        )

    run.status = "RUNNING"
    run.updated_at = utc_now()
    db.commit()
    db.refresh(run)

    return RunCreateResponse(run_id=run.id, status=run.status)  # type: ignore[arg-type]
