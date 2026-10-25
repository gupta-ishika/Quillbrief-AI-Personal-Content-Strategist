from collections.abc import Generator
from unittest.mock import patch

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import Approval
from app.db.repositories import create_run
from app.graph.state import ContentState
from app.services.background_worker import (
    CancellationManager,
    cancellation_manager,
    execute_graph_run,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def do_connect(dbapi_connection: object, connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(test_engine)


def test_cancellation_manager_lifecycle() -> None:
    mgr = CancellationManager()
    run_id = "run_test_123"

    assert not mgr.is_cancelled(run_id)

    mgr.register_run(run_id)
    assert not mgr.is_cancelled(run_id)

    success = mgr.request_cancellation(run_id)
    assert success is True
    assert mgr.is_cancelled(run_id)

    mgr.cleanup(run_id)
    assert not mgr.is_cancelled(run_id)


@pytest.mark.asyncio
async def test_execute_graph_run_cooperative_cancellation(db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")
    app_pending = Approval(run_id=run.id, item_type="plan", item_id="p1", status="PENDING")
    db_session.add(app_pending)
    db_session.commit()

    # Pre-cancel before execution to test early/step cancellation
    cancellation_manager.register_run(run.id)
    cancellation_manager.request_cancellation(run.id)

    with SqliteSaver.from_conn_string(":memory:") as checkpointer:
        await execute_graph_run(
            run_id=run.id,
            thread_id=run.thread_id,
            initial_state={"run_id": run.id, "user_goal": "test"},
            db_session=db_session,
            checkpointer=checkpointer,
        )

    db_session.refresh(run)
    db_session.refresh(app_pending)

    assert run.status == "STOPPED"
    assert run.stop_reason == "Cancelled by user"
    assert run.finished_at is not None
    assert app_pending.status == "CANCELLED"


@pytest.mark.asyncio
async def test_execute_graph_run_handles_interrupt(db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")

    # Build a graph that calls interrupt()
    def interrupt_node(state: ContentState) -> dict[str, str]:
        decision = interrupt({"review": "please review"})
        return {"approval_status": str(decision.get("decision", "APPROVED"))}

    workflow = StateGraph(ContentState)
    workflow.add_node("interrupter", interrupt_node)
    workflow.add_edge(START, "interrupter")
    workflow.add_edge("interrupter", END)

    with SqliteSaver.from_conn_string(":memory:") as checkpointer:
        compiled_graph = workflow.compile(checkpointer=checkpointer)

        with patch(
            "app.services.background_worker.create_content_graph", return_value=compiled_graph
        ):
            await execute_graph_run(
                run_id=run.id,
                thread_id=run.thread_id,
                initial_state={"run_id": run.id, "user_goal": "test"},
                db_session=db_session,
                checkpointer=checkpointer,
            )

    db_session.refresh(run)
    assert run.status == "WAITING_APPROVAL"


@pytest.mark.asyncio
async def test_execute_graph_run_handles_failure(db_session: Session) -> None:
    run = create_run(db_session, run_type="goal", depth_level="standard")

    def failing_node(state: ContentState) -> dict[str, str]:
        raise RuntimeError("Simulated unhandled model crash")

    workflow = StateGraph(ContentState)
    workflow.add_node("failing", failing_node)
    workflow.add_edge(START, "failing")
    workflow.add_edge("failing", END)

    with SqliteSaver.from_conn_string(":memory:") as checkpointer:
        compiled_graph = workflow.compile(checkpointer=checkpointer)

        with patch(
            "app.services.background_worker.create_content_graph", return_value=compiled_graph
        ):
            await execute_graph_run(
                run_id=run.id,
                thread_id=run.thread_id,
                initial_state={"run_id": run.id, "user_goal": "test"},
                db_session=db_session,
                checkpointer=checkpointer,
            )

    db_session.refresh(run)
    assert run.status == "FAILED"
    assert "Simulated unhandled model crash" in str(run.stop_reason)
    assert run.finished_at is not None
