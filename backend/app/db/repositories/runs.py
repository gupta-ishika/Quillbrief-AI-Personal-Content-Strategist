from typing import Any

from sqlalchemy.orm import Session

from app.db.base import generate_uuid, utc_now
from app.db.models import Goal, RoutingLog, Run, RunEvent, Task


def create_goal(db: Session, creator_id: str, text: str) -> Goal:
    goal = Goal(creator_id=creator_id, text=text)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def create_run(
    db: Session,
    run_type: str = "goal",
    depth_level: str = "standard",
    goal_id: str | None = None,
    thread_id: str | None = None,
) -> Run:
    run = Run(
        run_type=run_type,
        depth_level=depth_level,
        goal_id=goal_id,
        thread_id=thread_id or generate_uuid(),
        status="PENDING",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: str) -> Run | None:
    return db.query(Run).filter_by(id=run_id).first()


def update_run_status(
    db: Session,
    run_id: str,
    status: str,
    stop_reason: str | None = None,
    degraded: bool | None = None,
    degraded_reason: str | None = None,
) -> Run | None:
    run = get_run(db, run_id)
    if not run:
        return None
    run.status = status
    if status == "RUNNING" and not run.started_at:
        run.started_at = utc_now()
    elif status in ("COMPLETED", "FAILED", "STOPPED") and not run.finished_at:
        run.finished_at = utc_now()
    if stop_reason is not None:
        run.stop_reason = stop_reason
    if degraded is not None:
        run.degraded = degraded
    if degraded_reason is not None:
        run.degraded_reason = degraded_reason
    run.updated_at = utc_now()
    db.commit()
    db.refresh(run)
    return run


def create_task(db: Session, run_id: str, title: str, agent: str, position: int) -> Task:
    task = Task(run_id=run_id, title=title, agent=agent, position=position, status="TODO")
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task_status(db: Session, task_id: str, status: str) -> Task | None:
    task = db.query(Task).filter_by(id=task_id).first()
    if not task:
        return None
    task.status = status
    task.updated_at = utc_now()
    db.commit()
    db.refresh(task)
    return task


def get_run_tasks(db: Session, run_id: str) -> list[Task]:
    return db.query(Task).filter_by(run_id=run_id).order_by(Task.position.asc()).all()


def sync_run_tasks(
    db: Session,
    run_id: str,
    tasks_data: list[Any],
) -> list[Task]:
    """Synchronizes the supervisor's task list to the tasks table (GRAPH-06, DATABASE.md 3.3).

    Handles adding new tasks, updating status/title/agent, deleting removed tasks (unless DONE),
    and rewriting position numbers so they remain sequential 1..N.
    """
    existing_tasks = {t.id: t for t in db.query(Task).filter_by(run_id=run_id).all()}
    retained_ids: set[str] = set()
    result_tasks: list[Task] = []

    for idx, t_dict in enumerate(tasks_data, start=1):
        task_id = t_dict.get("id")
        title = str(t_dict.get("title") or f"Task {idx}")
        agent = str(t_dict.get("agent") or "supervisor")
        status = str(t_dict.get("status") or "TODO").upper()
        if status not in ("TODO", "DONE", "SKIPPED", "FAILED"):
            status = "TODO"

        if task_id and task_id in existing_tasks:
            task_obj = existing_tasks[task_id]
            task_obj.title = title
            task_obj.agent = agent
            task_obj.position = idx
            task_obj.status = status
            task_obj.updated_at = utc_now()
            retained_ids.add(task_id)
            result_tasks.append(task_obj)
        else:
            new_task = Task(
                run_id=run_id,
                title=title,
                agent=agent,
                position=idx,
                status=status,
            )
            db.add(new_task)
            result_tasks.append(new_task)

    # Delete unreferenced tasks that are not DONE
    for old_id, old_task in existing_tasks.items():
        if old_id not in retained_ids and old_task.status != "DONE":
            db.delete(old_task)

    db.commit()
    for t in result_tasks:
        db.refresh(t)

    return result_tasks


def create_routing_log(
    db: Session,
    run_id: str,
    step_number: int,
    from_node: str,
    to_node: str,
    reason: str,
    decided_by: str,
    eligible_nodes: list[str],
    output_status: str,
    invalid_category: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> RoutingLog:
    log = RoutingLog(
        run_id=run_id,
        step_number=step_number,
        from_node=from_node,
        to_node=to_node,
        reason=reason,
        decided_by=decided_by,
        eligible_nodes_json=eligible_nodes,
        output_status=output_status,
        invalid_category=invalid_category,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def record_run_event(
    db: Session,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> RunEvent:
    event = RunEvent(run_id=run_id, event_type=event_type, payload_json=payload)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
