"""Background execution service for graph runs (ARCHITECTURE.md Section 9.3 and BG-01).

Runs graphs in background workers with cooperative cancellation at step boundaries
and synchronized status transitions (RUNNING, WAITING_APPROVAL, COMPLETED, STOPPED, FAILED).
"""

import asyncio
import logging
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphInterrupt
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import Approval, Run
from app.db.repositories.runs import get_run, record_run_event, update_run_status
from app.db.session import SessionLocal
from app.graph.builder import create_content_graph
from app.graph.checkpointer import get_sqlite_checkpointer
from app.graph.state import ContentState

logger = logging.getLogger(__name__)


class CancellationManager:
    """Tracks cooperative cancellation events for active background runs."""

    def __init__(self) -> None:
        self._tokens: dict[str, asyncio.Event] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def register_run(self, run_id: str, task: asyncio.Task[Any] | None = None) -> asyncio.Event:
        event = asyncio.Event()
        self._tokens[run_id] = event
        if task:
            self._tasks[run_id] = task
        return event

    def set_task(self, run_id: str, task: asyncio.Task[Any]) -> None:
        self._tasks[run_id] = task

    def request_cancellation(self, run_id: str) -> bool:
        event = self._tokens.get(run_id)
        if event:
            event.set()
            return True
        return False

    def is_cancelled(self, run_id: str, db: Session | None = None) -> bool:
        event = self._tokens.get(run_id)
        if event and event.is_set():
            return True
        if db:
            run = db.query(Run).filter_by(id=run_id).first()
            if run and run.status == "STOPPED":
                return True
        return False

    def cleanup(self, run_id: str) -> None:
        self._tokens.pop(run_id, None)
        self._tasks.pop(run_id, None)


cancellation_manager = CancellationManager()


async def execute_graph_run(
    run_id: str,
    thread_id: str,
    initial_state: ContentState | None = None,
    resume_command: Any = None,
    db_session: Session | None = None,
    checkpointer: Any = None,
) -> None:
    """Executes a graph run cooperatively checking cancellation at step boundaries."""
    session = db_session or SessionLocal()
    checkpointer_cm = None

    try:
        # 1. Update run to RUNNING
        run = get_run(session, run_id)
        if not run:
            logger.error("Run '%s' not found for execution.", run_id)
            return

        if run.status in ("COMPLETED", "FAILED", "STOPPED"):
            logger.warning("Run '%s' already in terminal status '%s'.", run_id, run.status)
            return

        update_run_status(session, run_id, status="RUNNING")

        # 2. Prepare checkpointer and graph
        active_checkpointer = checkpointer
        if active_checkpointer is None:
            checkpointer_cm = get_sqlite_checkpointer()
            active_checkpointer = checkpointer_cm.__enter__()

        graph = create_content_graph(
            checkpointer=active_checkpointer,
            db_session=session,
        )

        config = {"configurable": {"thread_id": thread_id}}
        input_data = resume_command if resume_command is not None else initial_state

        # Check early cancellation before starting
        if cancellation_manager.is_cancelled(run_id, db=session):
            _handle_stopped(session, run_id)
            return

        # 3. Stream graph execution step by step
        try:
            is_async = (
                active_checkpointer is not None
                and hasattr(active_checkpointer, "aget_tuple")
                and not isinstance(active_checkpointer, SqliteSaver)
            )

            if is_async:
                async for chunk in graph.astream(input_data, config=config, stream_mode="updates"):
                    if cancellation_manager.is_cancelled(run_id, db=session):
                        logger.info(
                            "Run '%s' cooperative cancellation detected at step boundary.", run_id
                        )
                        _handle_stopped(session, run_id)
                        return
                    _process_chunk(session, run_id, chunk)
            else:
                for chunk in graph.stream(input_data, config=config, stream_mode="updates"):
                    if cancellation_manager.is_cancelled(run_id, db=session):
                        logger.info(
                            "Run '%s' cooperative cancellation detected at step boundary.", run_id
                        )
                        _handle_stopped(session, run_id)
                        return
                    _process_chunk(session, run_id, chunk)

            # Check if graph paused at a human approval interrupt
            state_snapshot = graph.get_state(config)
            has_interrupt = bool(
                state_snapshot.tasks and any(t.interrupts for t in state_snapshot.tasks)
            )
            if has_interrupt:
                logger.info("Run '%s' interrupted for human approval.", run_id)
                _handle_waiting_approval(session, run_id)
            else:
                _handle_completed(session, run_id)

        except GraphInterrupt:
            # Paused at human-in-the-loop interrupt
            logger.info("Run '%s' interrupted for human approval.", run_id)
            _handle_waiting_approval(session, run_id)

        except Exception as e:
            logger.exception("Error executing run '%s': %s", run_id, e)
            _handle_failed(session, run_id, str(e))

    finally:
        cancellation_manager.cleanup(run_id)
        if checkpointer_cm:
            try:
                checkpointer_cm.__exit__(None, None, None)
            except Exception:
                pass
        if not db_session:
            session.close()


def _process_chunk(session: Session, run_id: str, chunk: Any) -> None:
    if isinstance(chunk, dict):
        for _node_name, node_update in chunk.items():
            if isinstance(node_update, dict):
                step_count = node_update.get("execution_steps")
                tokens = node_update.get("tokens_used")
                degraded = node_update.get("degraded")
                degraded_reason = node_update.get("degraded_reason")
                if step_count is not None or tokens is not None:
                    r = get_run(session, run_id)
                    if r:
                        if step_count is not None:
                            r.step_count = step_count
                        if tokens is not None:
                            r.tokens_used = tokens
                        if degraded is not None:
                            r.degraded = degraded
                        if degraded_reason is not None:
                            r.degraded_reason = degraded_reason
                        session.commit()


def _handle_stopped(db: Session, run_id: str) -> None:
    run = get_run(db, run_id)
    if run and run.status not in ("COMPLETED", "FAILED", "STOPPED"):
        run.status = "STOPPED"
        run.stop_reason = "Cancelled by user"
        run.finished_at = utc_now()
        run.updated_at = utc_now()
        db.query(Approval).filter_by(run_id=run_id, status="PENDING").update(
            {"status": "CANCELLED"}
        )
        record_run_event(
            db,
            run_id,
            "note",
            {"message": "Run stopped cooperatively at step boundary."},
        )
        db.commit()


def _handle_waiting_approval(db: Session, run_id: str) -> None:
    run = get_run(db, run_id)
    if run and run.status not in ("STOPPED", "FAILED"):
        run.status = "WAITING_APPROVAL"
        run.updated_at = utc_now()
        db.commit()


def _handle_completed(db: Session, run_id: str) -> None:
    run = get_run(db, run_id)
    if run and run.status not in ("STOPPED", "FAILED"):
        run.status = "COMPLETED"
        run.finished_at = utc_now()
        run.updated_at = utc_now()
        db.commit()


def _handle_failed(db: Session, run_id: str, error_msg: str) -> None:
    run = get_run(db, run_id)
    if run and run.status not in ("STOPPED", "COMPLETED"):
        run.status = "FAILED"
        run.stop_reason = error_msg
        run.finished_at = utc_now()
        run.updated_at = utc_now()
        record_run_event(
            db,
            run_id,
            "tool_error",
            {"error": error_msg},
        )
        db.commit()


def start_background_run(
    run_id: str,
    thread_id: str,
    initial_state: ContentState | None = None,
    resume_command: Any = None,
    db_session: Session | None = None,
    checkpointer: Any = None,
) -> asyncio.Task[None]:
    """Starts graph execution asynchronously in the background."""
    cancellation_manager.register_run(run_id)
    task = asyncio.create_task(
        execute_graph_run(
            run_id=run_id,
            thread_id=thread_id,
            initial_state=initial_state,
            resume_command=resume_command,
            db_session=db_session,
            checkpointer=checkpointer,
        )
    )
    cancellation_manager.set_task(run_id, task)
    return task
